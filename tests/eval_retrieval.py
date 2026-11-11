"""
Retrieval Quality Evaluation and Latency Benchmarking Suite.
Evaluates Recall@1, Recall@3, Mean Reciprocal Rank (MRR), and Latency
across a benchmark test set of 20 realistic Discord server queries.
"""

import time
import tempfile
import shutil
import asyncio
from typing import List, Dict, Any, Tuple
import numpy as np

from rag_core.chunker import RecursiveCharacterChunker
from rag_core.embeddings import EmbeddingEngine
from rag_core.vector_store import VectorStore
from rag_core.rag_service import RAGService


# -------------------------------------------------------------
# 1. Ground Truth Knowledge Corpus (8 Realistic Server Documents)
# -------------------------------------------------------------
KNOWLEDGE_CORPUS = {
    "rules.md": (
        "Server Rules & Code of Conduct:\n"
        "1. Be respectful to all members. Harassment, hate speech, and toxicity will lead to immediate timeouts or bans.\n"
        "2. No unsolicited advertising, self-promotion, or DM advertising. Post invites only in designated channels.\n"
        "3. Keep discussions in the relevant channels. Keep memes in #memes and technical discussions in #development.\n"
        "4. Follow Discord Community Guidelines and Terms of Service at all times."
    ),
    "automod.md": (
        "Automated Moderation System:\n"
        "The server utilizes automated spam detection and invite filtering. "
        "Unauthorized Discord invite links are automatically purged, and the user receives a strike. "
        "Administrators can add blacklisted words via /automod add_word <word>, "
        "and remove words using /automod remove_word <word>. Members exceeding the rate limit receive a 5-minute timeout."
    ),
    "tickets.md": (
        "Ticket Support System & Dispute Resolution:\n"
        "To open a private support ticket or report a member, click the 'Create Ticket' button in #support-tickets. "
        "Staff can manage ticket panels using /tickets setup_panel. When a dispute is resolved, staff can click "
        "'Close Ticket' to generate a 1-click HTML transcript saved to server audit logs."
    ),
    "leveling.md": (
        "Chat Leveling & Role Progression:\n"
        "Members earn between 15-25 XP per message with a 60-second cooldown to discourage spam. "
        "Reaching Level 5 awards the 'Regular' badge role. "
        "Reaching Level 10 awards the prestigious 'VIP Member' role, unlocking exclusive voice rooms and beta channels. "
        "Check your current rank anytime using /rank or view the server leaderboard using /leaderboard."
    ),
    "voice.md": (
        "Voice Channels & Live Server Statistics:\n"
        "The server features dynamic join-to-create private voice rooms. "
        "Join the '➕ Create Channel' lobby to instantly spawn an auto-managed room with owner permissions. "
        "Live server statistics (member count, online counter, booster tally) are displayed in locked voice categories "
        "configured via /stats setup."
    ),
    "community.md": (
        "Community Events, Giveaways, and Polls:\n"
        "Server-wide giveaways are scheduled using /giveaway <duration> <prize> with button-click entries. "
        "Create community polls with up to 10 options using /poll <question>. "
        "If you are going away from chat, use /afk <reason> so other members are alerted if they mention you."
    ),
    "persona.txt": (
        "Bot Persona & Creator Guidelines:\n"
        "The bot's name is Miyu, a playful and loyal companion designed and created by server owner Kralveth. "
        "The bot only recognizes the server owner via verified owner tags. "
        "Discord bot limitations: Bots cannot execute slash commands for other bots (such as Disboard /bump); "
        "only human accounts have authorization to run application commands."
    ),
    "rag.md": (
        "Knowledge Base & RAG Commands:\n"
        "Admins can upload documentation files (.pdf, .md, .txt) using /rag upload <file>. "
        "To index historical messages from announcement or rules channels, use /rag index_channel <channel> [limit]. "
        "To test semantic search matches and cosine similarity percentages directly without calling the LLM, use /rag search <query>. "
        "View active memory usage, total chunks, and indexed sources using /rag docs."
    ),
}


# -------------------------------------------------------------
# 2. Evaluation Test Set (20 Questions with Ground-Truth Sources)
# -------------------------------------------------------------
EVAL_TEST_SET = [
    {
        "id": 1,
        "query": "How do I report a toxic member or open a private support ticket?",
        "ground_truth_source": "tickets.md",
        "expected_topic": "ticket support panel",
    },
    {
        "id": 2,
        "query": "What happens if someone sends an invite link to another Discord server?",
        "ground_truth_source": "automod.md",
        "expected_topic": "anti-invite filter",
    },
    {
        "id": 3,
        "query": "At what chat level do I unlock the VIP role reward?",
        "ground_truth_source": "leveling.md",
        "expected_topic": "Level 10 VIP Member",
    },
    {
        "id": 4,
        "query": "How do button giveaways work and what command creates them?",
        "ground_truth_source": "community.md",
        "expected_topic": "/giveaway command",
    },
    {
        "id": 5,
        "query": "How do I create my own private temporary voice room?",
        "ground_truth_source": "voice.md",
        "expected_topic": "join-to-create room",
    },
    {
        "id": 6,
        "query": "Who is the bot creator and owner according to the character persona?",
        "ground_truth_source": "persona.txt",
        "expected_topic": "Kralveth creator",
    },
    {
        "id": 7,
        "query": "Can the bot run slash commands like Disboard /bump for us?",
        "ground_truth_source": "persona.txt",
        "expected_topic": "Discord bots cannot run slash commands",
    },
    {
        "id": 8,
        "query": "How do administrators upload PDF documents into the knowledge base?",
        "ground_truth_source": "rag.md",
        "expected_topic": "/rag upload command",
    },
    {
        "id": 9,
        "query": "Where do I check server XP rankings and the top members leaderboard?",
        "ground_truth_source": "leveling.md",
        "expected_topic": "/rank and /leaderboard",
    },
    {
        "id": 10,
        "query": "What command allows staff to set up a support ticket panel in a channel?",
        "ground_truth_source": "tickets.md",
        "expected_topic": "/tickets setup_panel",
    },
    {
        "id": 11,
        "query": "How do admins test vector similarity search matches without calling the LLM?",
        "ground_truth_source": "rag.md",
        "expected_topic": "/rag search diagnostic",
    },
    {
        "id": 12,
        "query": "What are the rules regarding advertising and self-promotion in direct messages?",
        "ground_truth_source": "rules.md",
        "expected_topic": "unsolicited advertising",
    },
    {
        "id": 13,
        "query": "How can an administrator add blacklisted words to the automated filter?",
        "ground_truth_source": "automod.md",
        "expected_topic": "/automod add_word",
    },
    {
        "id": 14,
        "query": "How does the bot display live server member count statistics?",
        "ground_truth_source": "voice.md",
        "expected_topic": "/stats setup locked channels",
    },
    {
        "id": 15,
        "query": "What command should I use to notify people that I am away from keyboard?",
        "ground_truth_source": "community.md",
        "expected_topic": "/afk command",
    },
    {
        "id": 16,
        "query": "How does an admin index previous chat history from the announcements channel?",
        "ground_truth_source": "rag.md",
        "expected_topic": "/rag index_channel",
    },
    {
        "id": 17,
        "query": "What command creates community polls with voting options?",
        "ground_truth_source": "community.md",
        "expected_topic": "/poll command",
    },
    {
        "id": 18,
        "query": "What is the penalty for exceeding the spam rate limit?",
        "ground_truth_source": "automod.md",
        "expected_topic": "5-minute timeout strike",
    },
    {
        "id": 19,
        "query": "What happens when a staff member closes a resolved support ticket?",
        "ground_truth_source": "tickets.md",
        "expected_topic": "1-click HTML transcript",
    },
    {
        "id": 20,
        "query": "How can administrators check vector dimensions and total indexed chunks?",
        "ground_truth_source": "rag.md",
        "expected_topic": "/rag docs diagnostics",
    },
]


async def run_evaluation():
    temp_dir = tempfile.mkdtemp()
    try:
        service = RAGService()
        service.vector_store = VectorStore(storage_dir=temp_dir)

        print("\n=======================================================")
        print("  RAG RETRIEVAL QUALITY & LATENCY BENCHMARK")
        print("=======================================================")
        print(f"Indexing {len(KNOWLEDGE_CORPUS)} knowledge base documents...")

        # Ingest documents
        total_chunks = 0
        for doc_name, content in KNOWLEDGE_CORPUS.items():
            count = await service.ingest_text(content, source_name=doc_name, guild_id=1001)
            total_chunks += count

        print(f"Total chunks indexed: {total_chunks}")
        print(f"Vector Matrix Shape: {service.vector_store.matrix.shape}")
        print("Running 20-query evaluation...\n")

        top1_hits = 0
        top3_hits = 0
        reciprocal_ranks = []
        latencies_ms = []

        print(f"{'#':<3} | {'Query':<45} | {'Target':<12} | {'Rank':<6} | {'Top Match Score':<15} | {'Latency':<8}")
        print("-" * 100)

        for item in EVAL_TEST_SET:
            q_id = item["id"]
            query = item["query"]
            target = item["ground_truth_source"]

            # Benchmark retrieval latency with microsecond precision
            t_start = time.perf_counter()
            matches = await service.search(query, guild_id=1001, top_k=3, min_score=0.0)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            latencies_ms.append(elapsed_ms)

            # Check ranking of target source
            rank = None
            top_score = 0.0
            for r_idx, (chunk, score) in enumerate(matches, 1):
                if r_idx == 1:
                    top_score = score
                if chunk.metadata.get("source") == target:
                    rank = r_idx
                    break

            if rank == 1:
                top1_hits += 1
                top3_hits += 1
                reciprocal_ranks.append(1.0)
                rank_str = "Rank 1"
            elif rank is not None and rank <= 3:
                top3_hits += 1
                reciprocal_ranks.append(1.0 / rank)
                rank_str = f"Rank {rank}"
            else:
                reciprocal_ranks.append(0.0)
                rank_str = "MISS"

            short_q = query[:42] + "..." if len(query) > 45 else query
            print(f"{q_id:<3} | {short_q:<45} | {target:<12} | {rank_str:<6} | {top_score*100:>6.1f}%          | {elapsed_ms:>6.2f} ms")

        # Compute aggregate metrics
        n_queries = len(EVAL_TEST_SET)
        hit_rate_top1 = (top1_hits / n_queries) * 100.0
        hit_rate_top3 = (top3_hits / n_queries) * 100.0
        mrr = np.mean(reciprocal_ranks)
        avg_latency = np.mean(latencies_ms)
        p50_latency = np.median(latencies_ms)
        p95_latency = np.percentile(latencies_ms, 95)

        print("\n" + "=" * 55)
        print("          FINAL BENCHMARK EVALUATION RESULTS")
        print("=" * 55)
        print(f" Test Queries Evaluated : {n_queries}")
        print(f" Hit Rate @ Top-1       : {top1_hits}/{n_queries} ({hit_rate_top1:.1f}%)")
        print(f" Hit Rate @ Top-3       : {top3_hits}/{n_queries} ({hit_rate_top3:.1f}%)")
        print(f" Mean Reciprocal Rank   : {mrr:.3f}")
        print(f" Average Latency        : {avg_latency:.2f} ms")
        print(f" Median Latency (P50)   : {p50_latency:.2f} ms")
        print(f" 95th Percentile (P95)  : {p95_latency:.2f} ms")
        print("=" * 55 + "\n")

        return {
            "top1_hits": top1_hits,
            "top3_hits": top3_hits,
            "total": n_queries,
            "hit_rate_top1": hit_rate_top1,
            "hit_rate_top3": hit_rate_top3,
            "mrr": mrr,
            "avg_latency": avg_latency,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
