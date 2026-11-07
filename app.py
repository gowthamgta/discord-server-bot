"""Hugging Face Spaces entry point (Gradio SDK): runs the Discord bot in a thread and serves a status page."""
print("[app] Container started, loading Python modules...", flush=True)

# ZeroGPU: Hugging Face requires `import spaces` before any other heavy import (Gradio, torch, ...)
try:
    import spaces
except ImportError:
    spaces = None

import os
import signal
import asyncio
import threading
import inspect


def step(msg: str):
    # flush=True: container logs otherwise show nothing until the output buffer fills
    print(f"[app] {msg}", flush=True)


step(f"ZeroGPU package: {'loaded' if spaces else 'not installed (normal CPU Space)'}. Importing Gradio...")
import gradio as gr

# Disable bot's internal health server since Gradio handles port 7860
os.environ["HEALTH_SERVER_DISABLED"] = "1"

step("Importing the bot...")
import bot

# Launch Discord bot in a non-daemon thread so the process NEVER terminates
step("Starting the Discord bot thread...")
bot_thread = threading.Thread(target=bot.main, daemon=False)
bot_thread.start()


def _shutdown(signum, frame):
    """Hugging Face sends SIGTERM before restarting the Space: save data, then exit."""
    if bot.bot.loop and bot.bot.loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(bot.bot.close(), bot.bot.loop).result(timeout=25)
        except Exception:
            pass
    os._exit(0)


signal.signal(signal.SIGTERM, _shutdown)

# Satisfy ZeroGPU startup check
if spaces:
    @spaces.GPU
    def keep_gpu_happy(text):
        return text
else:
    def keep_gpu_happy(text):
        return text


def status_text() -> str:
    if bot.bot.is_ready():
        return f"🟢 **Online** as `{bot.bot.user}` in **{len(bot.bot.guilds)}** server(s) • latency {round(bot.bot.latency * 1000)} ms"
    return "🟡 **Starting…** (refresh in a few seconds)"


# Web interface for Hugging Face Spaces
with gr.Blocks(title="Discord Bot Status") as demo:
    gr.Markdown("# 🤖 Discord Bot Status")
    status = gr.Markdown(status_text())
    demo.load(status_text, outputs=status)

    # Hook the GPU function to an invisible event to satisfy the ZeroGPU detector
    dummy_in = gr.Textbox(visible=False, value="ok")
    dummy_out = gr.Textbox(visible=False)
    dummy_btn = gr.Button("Ping", visible=False)
    dummy_btn.click(fn=keep_gpu_happy, inputs=dummy_in, outputs=dummy_out)

launch_kwargs = {"server_name": "0.0.0.0", "server_port": 7860}
if "ssr_mode" in inspect.signature(demo.launch).parameters:
    launch_kwargs["ssr_mode"] = False

step("Launching the status page on port 7860...")
demo.launch(**launch_kwargs)
