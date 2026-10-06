"""Verification cog - public panel, session lifecycle, moderator review."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import is_guild_admin, is_moderator
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.verification.redaction import rex
from bot.verification.risk import RiskLevel
from bot.verification.service import VerificationService
from bot.verification.session import VState


# ---------------------------------------------------------------------------
# Public panel
# ---------------------------------------------------------------------------
class VerifyPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start Verification",
        style=discord.ButtonStyle.success,
        custom_id="verify:start",
    )
    async def start(self, interaction: discord.Interaction, _b: discord.ui.Button):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        sess = await svc.create_session(interaction.guild_id, interaction.user.id)
        if sess is None:
            return await interaction.response.send_message(
                "You are doing that too quickly. Please wait a moment.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="Verification started",
            description="Running security checks. This usually takes a few seconds.",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            verdict = await svc.verify(
                interaction.guild_id, interaction.user.id, sess.session_id,
            )
        except Exception as exc:
            await interaction.followup.send(
                "Verification service is temporarily unavailable. Please try again shortly.",
                ephemeral=True,
            )
            try:
                await svc.repo.log_event(
                    interaction.guild_id, interaction.user.id,
                    "verify_error", rex(exc),
                )
            except Exception:
                pass
            return

        await _finish(interaction, svc, sess.session_id, verdict)

    @discord.ui.button(
        label="I need help",
        style=discord.ButtonStyle.secondary,
        custom_id="verify:help",
    )
    async def help_btn(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await interaction.response.send_message(
            "If verification is not working, please open a support ticket.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Completion handler
# ---------------------------------------------------------------------------
async def _finish(interaction: discord.Interaction, svc: VerificationService,
                  session_id: str, verdict) -> None:
    guild = interaction.guild
    if guild is None:
        return
    gid = guild.id

    member = guild.get_member(interaction.user.id)
    if member is None:
        return

    verif_role_id = await svc.config.get(gid, "verify_role_id")
    quarantine_role_id = await svc.config.get(gid, "verify_quarantine_role_id")
    verif_role = (
        guild.get_role(int(verif_role_id))
        if verif_role_id and verif_role_id.isdigit() else None
    )
    quarantine_role = (
        guild.get_role(int(quarantine_role_id))
        if quarantine_role_id and quarantine_role_id.isdigit() else None
    )

    sess = await svc.sessions.get(session_id)
    if sess is None:
        return

    logging_svc = svc.logging

    base_fields = [
        ("Member", f"{member.mention} (`{member.id}`)", True),
        ("Risk score", f"`{verdict.risk_score}/100`", True),
        ("Risk level", f"`{verdict.risk_level.value}`", True),
        ("Confidence", f"`{verdict.confidence:.0%}`", True),
        ("Layer", f"`{int(verdict.required_layer.value)}`", True),
        ("Assessment ID", f"`{verdict.assessment_id or 0}`", True),
    ]

    signals = verdict.safe_reasons[:8]
    if signals:
        signals_text = "\n".join("- " + s for s in signals)
    else:
        signals_text = "- No significant signals"
    if len(verdict.safe_reasons) > 8:
        signals_text += "\n- ... and " + str(len(verdict.safe_reasons) - 8) + " more"

    # ---- LOW: pass ----
    if verdict.risk_level.value == "LOW":
        try:
            sess.transition(VState.CHALLENGE_REQUIRED)
            sess.transition(VState.CHALLENGE_ACTIVE)
            sess.transition(VState.COMPLETED)
        except Exception:
            pass

        if verif_role and verif_role not in member.roles:
            try:
                await member.add_roles(verif_role, reason="Verification passed")
            except discord.HTTPException:
                pass

        try:
            await svc.repo.record_attempt(gid, member.id, session_id, "PASSED", sess.layer)
        except Exception:
            pass
        try:
            await svc.repo.save_session(sess)
        except Exception:
            pass

        try:
            await logging_svc.emit(
                guild, "verification",
                title="Verification Passed",
                color=0x57F287,
                fields=base_fields + [
                    ("Signals", signals_text, False),
                    ("Action", "Standard verification complete", True),
                ],
            )
        except Exception:
            pass

        embed = discord.Embed(
            title="Verified",
            description="You now have access. Welcome aboard.",
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # ---- GUARDED / ELEVATED / HIGH: enhanced verification ----
    if verdict.risk_level.value in ("GUARDED", "ELEVATED", "HIGH"):
        try:
            sess.transition(VState.CHALLENGE_REQUIRED)
        except Exception:
            pass
        try:
            await svc.repo.save_session(sess)
        except Exception:
            pass
        try:
            await svc.repo.record_attempt(gid, member.id, session_id, "PENDING_REVIEW", sess.layer)
        except Exception:
            pass

        try:
            await logging_svc.emit(
                guild, "verification",
                title="Verification - Enhanced Required",
                color=0xFEE75C,
                fields=base_fields + [
                    ("Signals", signals_text, False),
                    ("Action", "Member routed to enhanced verification", False),
                    ("Recommendation", verdict.recommendation, False),
                ],
            )
        except Exception:
            pass

        embed = discord.Embed(
            title="Additional verification required",
            description=(
                "Your account has been routed to enhanced verification. "
                "Please open a support ticket and mention this message so a "
                "moderator can assist."
            ),
            color=0xFEE75C,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # ---- CRITICAL: quarantine ----
    try:
        sess.transition(VState.MANUAL_REVIEW)
    except Exception:
        pass

    if quarantine_role and quarantine_role not in member.roles:
        try:
            await member.add_roles(quarantine_role, reason="Quarantine")
        except discord.HTTPException:
            pass

    try:
        await svc.repo.record_attempt(gid, member.id, session_id, "QUARANTINED", sess.layer)
    except Exception:
        pass

    try:
        await svc.repo.record_review(
            gid, member.id, sess.assessment_id, "QUARANTINE",
            svc.bot.user.id if svc.bot.user else 0, "Automatic quarantine",
        )
    except Exception:
        pass

    try:
        await svc.repo.save_session(sess)
    except Exception:
        pass

    try:
        await logging_svc.emit(
            guild, "verification",
            title="Verification - Quarantined",
            color=0xED4245,
            fields=base_fields + [
                ("Signals", signals_text, False),
                ("Action", "Member quarantined, pending moderator review", False),
                ("Review", "Use /verify-review to approve, reject, or release", False),
            ],
        )
    except Exception:
        pass

    embed = discord.Embed(
        title="Manual review required",
        description=(
            "Your account has been placed in quarantine while a moderator "
            "reviews it. You will be notified once a decision has been made."
        ),
        color=0xED4245,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Moderator review
# ---------------------------------------------------------------------------
class ReviewView(discord.ui.View):
    def __init__(self, *, guild_id: int, user_id: int,
                 assessment_id: Optional[int], author_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.user_id = user_id
        self.assessment_id = assessment_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        perms = interaction.user.guild_permissions
        if not (perms.moderate_members or perms.administrator):
            await interaction.response.send_message("Moderator only.", ephemeral=True)
            return False
        return True

    async def _apply(self, interaction: discord.Interaction, decision: str,
                     remove_quarantine: bool, add_verified: bool):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        guild = interaction.guild
        if guild is None:
            return

        try:
            await svc.repo.record_review(
                guild.id, self.user_id, self.assessment_id,
                decision, interaction.user.id, "",
            )
        except Exception:
            pass

        try:
            await svc.repo.log_event(
                guild.id, self.user_id, "review",
                "decision=" + decision + " mod=" + str(interaction.user.id),
            )
        except Exception:
            pass

        member = guild.get_member(self.user_id)
        if member is not None:
            qid = await svc.config.get(guild.id, "verify_quarantine_role_id")
            vid = await svc.config.get(guild.id, "verify_role_id")
            qrole = guild.get_role(int(qid)) if qid and qid.isdigit() else None
            vrole = guild.get_role(int(vid)) if vid and vid.isdigit() else None

            try:
                if remove_quarantine and qrole and qrole in member.roles:
                    await member.remove_roles(qrole, reason="Review: " + decision)
                if add_verified and vrole and vrole not in member.roles:
                    await member.add_roles(vrole, reason="Review: " + decision)
            except discord.HTTPException:
                pass

        try:
            if decision == "APPROVE":
                color = 0x57F287
            elif decision == "REJECT":
                color = 0xED4245
            else:
                color = 0x5865F2

            await svc.logging.emit(
                guild, "verification",
                title="Verification Review - " + decision,
                color=color,
                fields=[
                    ("Member", "<@" + str(self.user_id) + "> (`" + str(self.user_id) + "`)", True),
                    ("Moderator", interaction.user.mention, True),
                    ("Decision", "`" + decision + "`", True),
                    ("Assessment ID", "`" + str(self.assessment_id or 0) + "`", True),
                ],
            )
        except Exception:
            pass

        await interaction.response.send_message(
            "Decision recorded: " + decision, ephemeral=True,
        )

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await self._apply(interaction, "APPROVE", remove_quarantine=True, add_verified=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await self._apply(interaction, "REJECT", remove_quarantine=False, add_verified=False)

    @discord.ui.button(label="Release", style=discord.ButtonStyle.primary)
    async def release(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await self._apply(interaction, "RELEASE", remove_quarantine=True, add_verified=False)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary)
    async def reset(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await self._apply(interaction, "RESET_VERIFICATION", remove_quarantine=True, add_verified=False)


# ---------------------------------------------------------------------------
# The cog
# ---------------------------------------------------------------------------
class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigService(bot.db)
        logging_svc = LoggingService(bot.db)

        self.service = VerificationService(
            bot=bot,
            db=bot.db,
            config_service=self.config,
            logging_service=logging_svc,
            session_timeout=int(os.getenv("VERIFY_SESSION_TIMEOUT", "900")),
        )
        bot.verification = self.service  # expose to views

    async def cog_load(self) -> None:
        self.bot.add_view(VerifyPanelView())
        self._cleanup.start()

    def cog_unload(self) -> None:
        self._cleanup.cancel()

    @tasks.loop(minutes=5)
    async def _cleanup(self) -> None:
        try:
            await self.service.sessions.cleanup_expired()
        except Exception:
            pass

    @_cleanup.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    # ---- Event hooks ----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        now = datetime.now(timezone.utc)
        age_days = max((now - member.created_at).days, 0)
        try:
            self.service.on_member_join(member, age_days)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        try:
            self.service.on_message(message)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if len(after.roles) > len(before.roles):
            try:
                self.service.on_role_add(after.guild.id, after.id)
            except Exception:
                pass

    # ---- Commands ----
    @app_commands.command(name="verify", description="Start verification.")
    async def verify(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        sess = await self.service.create_session(interaction.guild_id, interaction.user.id)
        if sess is None:
            return await interaction.response.send_message(
                "Too many attempts. Try again later.", ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        try:
            verdict = await self.service.verify(
                interaction.guild_id, interaction.user.id, sess.session_id,
            )
        except Exception as exc:
            await interaction.followup.send(
                "Verification service unavailable. Please try again.", ephemeral=True,
            )
            try:
                await self.service.repo.log_event(
                    interaction.guild_id, interaction.user.id, "verify_error", rex(exc),
                )
            except Exception:
                pass
            return

        await _finish(interaction, self.service, sess.session_id, verdict)

    @app_commands.command(name="verification-panel",
                          description="Post the public verification panel.")
    @is_guild_admin()
    async def verification_panel(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Use in a text channel.", ephemeral=True,
            )
        embed = discord.Embed(
            title="Verification",
            description=(
                "Press the button below to verify your account and gain access "
                "to the server."
            ),
            color=0x5865F2,
        )
        await interaction.channel.send(embed=embed, view=VerifyPanelView())
        await interaction.response.send_message("Panel posted.", ephemeral=True)

    @app_commands.command(name="verify-status",
                          description="Show the verification state for a member.")
    @is_moderator()
    async def verify_status(self, interaction: discord.Interaction,
                            member: discord.Member):
        if interaction.guild_id is None:
            return
        row = await self.service.repo.latest_assessment(interaction.guild_id, member.id)
        if not row:
            return await interaction.response.send_message(
                "No assessment on record.", ephemeral=True,
            )
        embed = discord.Embed(title="Verification status - " + str(member), color=0x5865F2)
        embed.add_field(name="Risk score", value=str(row["risk_score"]) + "/100", inline=True)
        embed.add_field(name="Risk level", value=str(row["risk_level"]), inline=True)
        embed.add_field(name="Confidence", value=format(float(row["confidence"]), ".0%"), inline=True)
        embed.add_field(name="Layer", value=str(row["required_layer"]), inline=True)
        embed.add_field(name="Recommendation", value=row["recommendation"] or "-", inline=False)
        if row["families_json"]:
            embed.add_field(name="Signal families", value=str(row["families_json"]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verify-review",
                          description="Open a moderator review panel for a member.")
    @is_moderator()
    async def verify_review(self, interaction: discord.Interaction,
                            member: discord.Member):
        if interaction.guild_id is None:
            return
        row = await self.service.repo.latest_assessment(interaction.guild_id, member.id)
        embed = discord.Embed(title="Security assessment - " + str(member), color=0x5865F2)
        if row:
            embed.add_field(name="Risk score", value=str(row["risk_score"]) + "/100", inline=True)
            embed.add_field(name="Risk level", value=str(row["risk_level"]), inline=True)
            embed.add_field(name="Confidence", value=format(float(row["confidence"]), ".0%"), inline=True)
            embed.add_field(name="Layer", value=str(row["required_layer"]), inline=True)
            embed.add_field(name="Assessment ID", value=str(row["id"]), inline=True)
            embed.add_field(name="Recommendation", value=row["recommendation"] or "-", inline=False)
        else:
            embed.description = "No assessment on record for this member."
        view = ReviewView(
            guild_id=interaction.guild_id,
            user_id=member.id,
            assessment_id=row["id"] if row else None,
            author_id=interaction.user.id,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="verification-config",
                          description="Configure the verification system.")
    @is_guild_admin()
    async def verification_config(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if gid is None:
            return
        embed = discord.Embed(title="Verification configuration", color=0x5865F2)
        for label, key in [
            ("Verification role", "verify_role_id"),
            ("Quarantine role", "verify_quarantine_role_id"),
            ("Log channel", "verify_log_channel_id"),
        ]:
            raw = await self.config.get(gid, key)
            shown = "not set"
            if raw and raw.isdigit() and interaction.guild:
                obj = interaction.guild.get_role(int(raw)) or interaction.guild.get_channel(int(raw))
                if obj is not None:
                    shown = obj.mention
            embed.add_field(name=label, value=shown, inline=True)
        embed.set_footer(text="Use the commands below to configure.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verification-role",
                          description="Set the role given on successful verification.")
    @is_guild_admin()
    async def verification_role(self, interaction: discord.Interaction,
                                role: discord.Role):
        await self.config.set(interaction.guild_id, "verify_role_id", role.id)
        await interaction.response.send_message(
            "Verification role set to " + role.mention + ".", ephemeral=True,
        )

    @app_commands.command(name="verification-quarantine-role",
                          description="Set the quarantine role.")
    @is_guild_admin()
    async def verification_quarantine_role(self, interaction: discord.Interaction,
                                           role: discord.Role):
        await self.config.set(interaction.guild_id, "verify_quarantine_role_id", role.id)
        await interaction.response.send_message(
            "Quarantine role set to " + role.mention + ".", ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
