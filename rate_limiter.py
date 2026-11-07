import asyncio
import time
import logging
from collections import deque
from typing import Callable, Any
import aiohttp
import config

logger = logging.getLogger("RateLimiter")

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# --- Model choice (measured 2026-10-27 on this project's keys) ---
# Chat: fast "lite" models first. They answer in ~1s and have the biggest free daily quotas.
GEMINI_CHAT_MODELS = [
    "gemini-3.5-flash-lite",     # ~0.8s
    "gemini-flash-lite-latest",  # ~1.1s, alias that follows Google's newest lite model
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",    # ~2s, smarter, smaller quota
]
# Quality: rare, important requests (AI server design, owner action parsing) use the smarter models first.
GEMINI_QUALITY_MODELS = [
    "gemini-3-flash-preview",    # ~2s
    "gemini-3.5-flash",          # ~6s
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
]
# Groq fallback: each model has its own 1,000 requests/day and 8,000 tokens/min (from Groq's response headers).
GROQ_MODELS = [
    "qwen/qwen3.8-27b",          # ~0.4s
    "openai/gpt-oss-120b",       # ~0.4s
    "openai/gpt-oss-20b",        # ~0.8s
]

GEMINI_TIMEOUT_SECONDS = 25     # Server-design JSON can take a while; chat replies take a few seconds
GROQ_TIMEOUT_SECONDS = 15
CHAT_MAX_TOKENS = 600           # Kralveth keeps replies short; this also saves Groq's tokens/min budget
JSON_MAX_TOKENS = 4096

# How long to skip a model after it fails, so we don't waste requests on it
COOLDOWN_RATE_LIMIT = 65        # per-minute quota hit
COOLDOWN_DAILY_LIMIT = 3600     # per-day quota hit: check again in an hour
COOLDOWN_OVERLOADED = 30        # 503 / 504 / timeout


class QueueFullError(Exception):
    """Raised when the backpressure queue exceeds its limit."""
    pass


class UserCooldownError(Exception):
    """Raised when a specific user is on cooldown."""
    def __init__(self, remaining_seconds: float):
        self.remaining_seconds = remaining_seconds
        super().__init__(f"User cooldown active: wait {remaining_seconds:.1f}s")


def _cooldown_for(err_text: str) -> int:
    text = err_text.lower()
    if "429" in text or "resource_exhausted" in text or "quota" in text or "rate limit" in text:
        return COOLDOWN_DAILY_LIMIT if "perday" in text or "per day" in text else COOLDOWN_RATE_LIMIT
    if any(code in text for code in ("503", "504", "500", "unavailable", "deadline", "overloaded", "timeout")):
        return COOLDOWN_OVERLOADED
    return 0  # e.g. a bad request; not the model's fault, don't bench it


class GeminiRateLimiter:
    """
    AI request gateway for the free tiers:
    1. Gemini models first (chat or quality list), Groq models as fallback
    2. Per-model cooldowns: a throttled/overloaded model is skipped and the next one is tried
    3. Global sliding window + concurrency cap + per-user cooldown + backpressure queue
    """
    def __init__(
        self,
        interval_cap: int = 15,            # requests per rolling window, across all models
        interval_seconds: float = 60.0,
        concurrency: int = 3,              # max simultaneous API calls
        max_queue_size: int = 20,          # reject new requests beyond this backlog
        user_cooldown_seconds: float = 4.0
    ):
        self.interval_cap = interval_cap
        self.interval_seconds = interval_seconds
        self.concurrency = concurrency
        self.max_queue_size = max_queue_size
        self.user_cooldown_seconds = user_cooldown_seconds

        self._timestamps = deque()         # Sliding log of execution timestamps
        self._queue = asyncio.Queue()
        self._user_cooldowns = {}          # {user_id: timestamp}
        self._model_cooldowns = {}         # {model: unix time it may be used again}
        self._worker_task = None
        self._semaphore = asyncio.Semaphore(concurrency)
        self._client = None
        self._init_client()

    def _init_client(self):
        api_key = getattr(config, "GEMINI_API_KEY", "").strip()
        if GENAI_AVAILABLE and api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
            try:
                self._client = genai.Client(api_key=api_key, http_options={"timeout": GEMINI_TIMEOUT_SECONDS * 1000})
            except Exception:
                self._client = None
        else:
            self._client = None

    def refresh_client(self):
        self._init_client()

    @property
    def is_groq_active(self) -> bool:
        key = getattr(config, "GROQ_API_KEY", "").strip()
        return bool(key and key != "YOUR_GROQ_API_KEY_HERE")

    @property
    def is_gemini_active(self) -> bool:
        """Returns True if either Gemini or Groq fallback is ready."""
        return self._client is not None or self.is_groq_active

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def load(self) -> float:
        """How busy the AI is, 0.0 (idle) to 1.0 (minute budget used up or queue full)."""
        now = time.time()
        used = sum(1 for t in self._timestamps if now - t < self.interval_seconds) / max(self.interval_cap, 1)
        return min(1.0, max(used, self.queue_size / max(self.max_queue_size, 1)))

    def model_status(self) -> dict:
        """{model: seconds until usable} for models currently cooling down."""
        now = time.time()
        return {m: int(t - now) for m, t in self._model_cooldowns.items() if t > now}

    def _available(self, model: str) -> bool:
        return self._model_cooldowns.get(model, 0) <= time.time()

    def _bench(self, model: str, err: Exception | str):
        seconds = _cooldown_for(str(err))
        if seconds:
            self._model_cooldowns[model] = time.time() + seconds
            logger.warning(f"{model} unavailable ({str(err)[:80]}); skipping it for {seconds}s")

    def check_user_cooldown(self, user_id: int) -> float:
        """Returns 0 if user is allowed, or seconds remaining if on cooldown."""
        now = time.time()
        if user_id in self._user_cooldowns:
            elapsed = now - self._user_cooldowns[user_id]
            if elapsed < self.user_cooldown_seconds:
                return self.user_cooldown_seconds - elapsed
        self._user_cooldowns[user_id] = now
        return 0.0

    async def execute(self, coro_fn: Callable[[], Any], user_id: int = None) -> Any:
        """Dispatches a coroutine through the rate-limited sliding window queue."""
        if user_id is not None:
            remaining = self.check_user_cooldown(user_id)
            if remaining > 0:
                raise UserCooldownError(remaining)

        if self._queue.qsize() >= self.max_queue_size:
            raise QueueFullError(
                f"The bot is currently experiencing heavy load ({self._queue.qsize()} queries waiting). Please try again in a minute."
            )

        future = asyncio.get_running_loop().create_future()
        await self._queue.put((coro_fn, future))

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())

        return await future

    async def _process_queue(self):
        while True:
            coro_fn, future = await self._queue.get()
            now = time.time()

            # Evict timestamps older than the sliding window
            while self._timestamps and now - self._timestamps[0] >= self.interval_seconds:
                self._timestamps.popleft()

            # At the cap: wait until the oldest request leaves the window
            if len(self._timestamps) >= self.interval_cap:
                oldest = self._timestamps[0]
                await asyncio.sleep(max(0.1, (oldest + self.interval_seconds) - now + 0.1))
                now = time.time()
                while self._timestamps and now - self._timestamps[0] >= self.interval_seconds:
                    self._timestamps.popleft()

            self._timestamps.append(time.time())
            asyncio.create_task(self._run_task(coro_fn, future))
            self._queue.task_done()

    async def _run_task(self, coro_fn, future):
        async with self._semaphore:
            try:
                res = await coro_fn()
                if not future.done():
                    future.set_result(res)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)

    async def _call_gemini(self, model: str, prompt: str, json_mode: bool) -> str:
        gen_config = {"response_mime_type": "application/json"} if json_mode else None
        # The client has its own HTTP timeout; wait_for is a backstop so a stuck call can't hold a queue slot
        resp = await asyncio.wait_for(
            asyncio.to_thread(self._client.models.generate_content, model=model, contents=prompt, config=gen_config),
            timeout=GEMINI_TIMEOUT_SECONDS + 5,
        )
        text = (resp.text or "").strip() if resp else ""
        if not text:
            raise RuntimeError(f"{model} returned an empty response")
        return text

    async def _call_groq(self, model: str, prompt: str, json_mode: bool) -> str:
        api_key = getattr(config, "GROQ_API_KEY", "").strip()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": JSON_MAX_TOKENS if json_mode else CHAT_MAX_TOKENS,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"  # hidden reasoning also counts against the token budget

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "DiscordBot/1.0"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=GROQ_TIMEOUT_SECONDS)) as session:
            async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Groq HTTP {resp.status}: {(await resp.text())[:150]}")
                data = await resp.json()
        text = (data["choices"][0]["message"].get("content") or "").strip()
        if not text:
            raise RuntimeError(f"{model} returned an empty response")
        return text

    async def ask_gemini(self, prompt: str, user_id: int = None, json_mode: bool = False, quality: bool = False) -> str:
        """
        Sends a prompt through the queue and returns the first good answer.
        Order: Gemini (chat or quality list) -> Groq, skipping any model that is cooling down.
        """
        if not self._client:
            self.refresh_client()
        if not self._client and not self.is_groq_active:
            raise RuntimeError("No AI service configured. Add your GEMINI_API_KEY or GROQ_API_KEY.")

        candidates = []
        if self._client:
            candidates += [("gemini", m) for m in (GEMINI_QUALITY_MODELS if quality else GEMINI_CHAT_MODELS)]
        if self.is_groq_active:
            candidates += [("groq", m) for m in GROQ_MODELS]

        async def _call_api():
            last_err = None
            available = [c for c in candidates if self._available(c[1])] or candidates  # all benched: try anyway
            for provider, model in available:
                try:
                    if provider == "gemini":
                        return await self._call_gemini(model, prompt, json_mode)
                    return await self._call_groq(model, prompt, json_mode)
                except asyncio.TimeoutError as e:
                    last_err = RuntimeError(f"{model} timeout")
                    self._bench(model, "timeout")
                except Exception as e:
                    last_err = e
                    self._bench(model, e)
            raise last_err or RuntimeError("All AI models failed.")

        return await self.execute(_call_api, user_id=user_id)


# Global singleton for the whole bot
gemini_queue = GeminiRateLimiter()
