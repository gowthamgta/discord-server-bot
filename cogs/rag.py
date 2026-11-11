"""
RAG (Retrieval-Augmented Generation) Cog.
Provides slash commands for document ingestion, channel indexing, semantic search,
and grounded question answering with source citations.
"""

import io
import time
import logging
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from config import (
    EMBED_COLOR_AI,
    EMBED_COLOR_SUCCESS,
    EMBED_COLOR_ERROR,
    EMBED_COLOR_WARNING,
    EMBED_COLOR_DEFAULT,
)
from rag_core.rag_service import rag_service

logger = logging.getLogger("Cog.RAG")


class RAGCog(commands.Cog, name="Knowledge Base & RAG"):
    """Server knowledge base and intelligent question answering."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Create /rag command group for administrative management
    rag_group = app_commands.Group(
        name="rag",
        description="Manage the server RAG knowledge base, documents, and channel indexing",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ---------------------------------------------------------
    # Public Slash Command: /ask
    # ---------------------------------------------------------
    @app_commands.command(
        name="ask",
        description="Ask a question answered strictly from the server's knowledge base and documentation.",
    )
    @app_commands.describe(
        question="What would you like to know?",
        ephemeral="Only show the answer to you (default: False)",
    )
    async def ask(
        self,
        interaction: discord.Interaction,
        question: str,
        ephemeral: bool = False,
    ):
        """Retrieves relevant server knowledge and answers using grounded RAG."""
        await interaction.response.defer(ephemeral=ephemeral)

        guild_id = interaction.guild.id if interaction.guild else None
        result = await rag_service.answer_question(
            query=question,
            guild_id=guild_id,
            top_k=4,
            min_score=0.28,
        )

        answer_text = result["answer"]
        sources = result["sources"]
        confidence = result["confidence"]
        latency_ms = result["latency_ms"]
        chunks_count = result["chunks_used"]

        embed = discord.Embed(
            title="🧠 Server Knowledge Assistant",
            description=answer_text,
            color=EMBED_COLOR_AI,
        )
        embed.add_field(name="❓ Question", value=f"*{question[:250]}*", inline=False)

        if sources:
            source_lines = []
            for s in sources:
                source_lines.append(f"• **{s['source']}** ({s['score']}% match)")
            embed.add_field(
                name="📚 Sources & Evidence",
                value="\n".join(source_lines[:6]),
                inline=False,
            )

        footer_text = f"Retrieved {chunks_count} chunks • {latency_ms}ms"
        if confidence > 0:
            footer_text += f" • Avg Confidence: {confidence}%"
        embed.set_footer(text=footer_text, icon_url=self.bot.user.display_avatar.url if self.bot.user else None)

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    # ---------------------------------------------------------
    # Admin Subcommand: /rag upload
    # ---------------------------------------------------------
    @rag_group.command(
        name="upload",
        description="Upload a document (.pdf, .txt, .md, .json) to the server knowledge base.",
    )
    @app_commands.describe(
        file="The document file to index",
        title="Optional custom title for the document",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def upload(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        title: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        supported_extensions = (".pdf", ".txt", ".md", ".markdown", ".json", ".csv", ".log", ".py")
        if not any(file.filename.lower().endswith(ext) for ext in supported_extensions):
            return await interaction.followup.send(
                f"❌ Unsupported file type. Supported extensions: `{', '.join(supported_extensions)}`",
                ephemeral=True,
            )

        if file.size > 15 * 1024 * 1024:  # 15MB limit
            return await interaction.followup.send(
                "❌ File size exceeds the 15 MB limit.",
                ephemeral=True,
            )

        try:
            file_bytes = await file.read()
            doc_name = title or file.filename
            guild_id = interaction.guild.id if interaction.guild else None

            start = time.time()
            chunk_count = await rag_service.ingest_file(
                file_bytes=file_bytes,
                filename=doc_name,
                guild_id=guild_id,
                extra_meta={"uploader_id": interaction.user.id, "file_url": file.url},
            )
            elapsed = round((time.time() - start) * 1000, 1)

            if chunk_count == 0:
                return await interaction.followup.send(
                    f"⚠️ File `{doc_name}` was read, but no readable text chunks could be extracted.",
                    ephemeral=True,
                )

            embed = discord.Embed(
                title="📄 Document Indexed Successfully",
                description=f"File **`{doc_name}`** has been embedded and added to the server vector store.",
                color=EMBED_COLOR_SUCCESS,
            )
            embed.add_field(name="Chunks Created", value=str(chunk_count), inline=True)
            embed.add_field(name="File Size", value=f"{round(file.size / 1024, 1)} KB", inline=True)
            embed.add_field(name="Indexing Latency", value=f"{elapsed} ms", inline=True)
            embed.set_footer(text=f"Uploaded by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /rag upload: {e}")
            await interaction.followup.send(f"❌ Failed to process document: {e}", ephemeral=True)

    # ---------------------------------------------------------
    # Admin Subcommand: /rag index_channel
    # ---------------------------------------------------------
    @rag_group.command(
        name="index_channel",
        description="Index messages from a Discord channel (e.g. #rules, #announcements, #faq).",
    )
    @app_commands.describe(
        channel="The text channel to index",
        limit="Maximum messages to scan (default: 150)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def index_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: int = 150,
    ):
        await interaction.response.defer(ephemeral=True)

        if limit > 500:
            limit = 500

        try:
            start = time.time()
            chunk_count = await rag_service.ingest_discord_channel(
                channel=channel,
                limit=limit,
                guild_id=interaction.guild.id if interaction.guild else None,
            )
            elapsed = round((time.time() - start) * 1000, 1)

            if chunk_count == 0:
                return await interaction.followup.send(
                    f"⚠️ Scanned {channel.mention}, but found no text messages to index.",
                    ephemeral=True,
                )

            embed = discord.Embed(
                title="📡 Channel Indexed Successfully",
                description=f"Channel {channel.mention} has been ingested into the vector knowledge base.",
                color=EMBED_COLOR_SUCCESS,
            )
            embed.add_field(name="Messages Scanned", value=str(limit), inline=True)
            embed.add_field(name="Chunks Vectorized", value=str(chunk_count), inline=True)
            embed.add_field(name="Processing Time", value=f"{elapsed} ms", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /rag index_channel: {e}")
            await interaction.followup.send(f"❌ Failed to index channel: {e}", ephemeral=True)

    # ---------------------------------------------------------
    # Admin Subcommand: /rag add_snippet
    # ---------------------------------------------------------
    @rag_group.command(
        name="add_snippet",
        description="Add a short knowledge snippet, rule, or FAQ entry directly to the knowledge base.",
    )
    @app_commands.describe(
        title="Title or identifier for this knowledge snippet",
        content="The facts, guidelines, or FAQ content to store",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_snippet(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
    ):
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id if interaction.guild else None
        chunks_count = await rag_service.ingest_text(
            text=content,
            source_name=f"Snippet: {title}",
            guild_id=guild_id,
            extra_meta={"author_id": interaction.user.id, "snippet_title": title},
        )

        embed = discord.Embed(
            title="📝 Knowledge Snippet Added",
            description=f"Indexed **`{title}`** into vector store ({chunks_count} chunk(s)).",
            color=EMBED_COLOR_SUCCESS,
        )
        embed.add_field(name="Content Preview", value=f"{content[:300]}...", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # Diagnostic Subcommand: /rag search
    # ---------------------------------------------------------
    @rag_group.command(
        name="search",
        description="Test vector similarity search and inspect retrieved chunks with similarity scores.",
    )
    @app_commands.describe(
        query="The search query to test against vector embeddings",
        top_k="Number of chunks to retrieve (default: 3)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def search(
        self,
        interaction: discord.Interaction,
        query: str,
        top_k: int = 3,
    ):
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id if interaction.guild else None
        matches = await rag_service.search(query=query, guild_id=guild_id, top_k=top_k, min_score=0.1)

        if not matches:
            return await interaction.followup.send(
                f"No vector matches found for `{query}`.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title=f"🔍 Vector Search Test: '{query[:50]}'",
            color=EMBED_COLOR_DEFAULT,
        )
        for i, (chunk, score) in enumerate(matches, 1):
            src = chunk.metadata.get("source", "unknown")
            pct = round(score * 100, 1)
            preview = chunk.content[:180].replace("\n", " ")
            embed.add_field(
                name=f"#{i} [{pct}%] - {src}",
                value=f"```{preview}...```",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # Admin Subcommand: /rag docs
    # ---------------------------------------------------------
    @rag_group.command(
        name="docs",
        description="View all indexed documents, total chunks, and knowledge store diagnostics.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def docs(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else None
        stats = rag_service.get_stats(guild_id=guild_id)

        embed = discord.Embed(
            title="📊 Knowledge Base Diagnostics",
            color=EMBED_COLOR_DEFAULT,
        )
        embed.add_field(name="Total Chunks", value=str(stats["total_chunks"]), inline=True)
        embed.add_field(name="Unique Sources", value=str(stats["unique_sources"]), inline=True)
        embed.add_field(name="Vector Dimension", value=f"{stats['dimension']}D", inline=True)
        embed.add_field(name="Vector Memory", value=f"{stats['memory_kb']} KB", inline=True)

        sources = stats["sources"]
        if sources:
            source_lines = [f"• `{src}` ({count} chunks)" for src, count in list(sources.items())[:12]]
            embed.add_field(
                name="Indexed Sources",
                value="\n".join(source_lines),
                inline=False,
            )
        else:
            embed.description = "No documents currently indexed. Use `/rag upload` or `/rag index_channel` to add knowledge."

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------
    # Admin Subcommand: /rag delete_doc
    # ---------------------------------------------------------
    @rag_group.command(
        name="delete_doc",
        description="Remove a specific document or channel source from the knowledge store.",
    )
    @app_commands.describe(source="Exact source name as shown in /rag docs (e.g. 'rules.pdf' or '#announcements')")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_doc(self, interaction: discord.Interaction, source: str):
        guild_id = interaction.guild.id if interaction.guild else None
        deleted = rag_service.delete_source(source=source, guild_id=guild_id)

        if deleted > 0:
            await interaction.response.send_message(
                f"✅ Removed `{source}` ({deleted} chunks deleted) from the knowledge base.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ Source `{source}` was not found in the knowledge base.",
                ephemeral=True,
            )

    # ---------------------------------------------------------
    # Admin Subcommand: /rag clear
    # ---------------------------------------------------------
    @rag_group.command(
        name="clear",
        description="Purge all indexed knowledge base vectors for this server.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clear(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else None
        deleted = rag_service.clear(guild_id=guild_id)
        await interaction.response.send_message(
            f"🧹 Knowledge base cleared. Removed {deleted} chunks for this server.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RAGCog(bot))
    logger.info("RAGCog loaded successfully.")
