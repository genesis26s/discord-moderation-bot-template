"""Verification cog - full lifecycle, UI, moderation review."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import is_guild_admin, is_moderator
from bot.services.config_service import ConfigService
from bot.services.logging_service import LoggingService
from bot.verification.redaction import rex
from bot.verification.service import VerificationService
from bot.verification.session import VState


class RobloxLinkModal(discord.ui.Modal):
    def __init__(self, *, guild_id: int, user_id: int):
        super().__init__(title="Link Roblox account")
        self.guild_id = guild_id
        self.user_id = user_id
        self.username_input = discord.ui.TextInput(
            label="Roblox username",
            placeholder="Your Roblox username (not display name)",
            max_length=32,
            required=True,
        )
        self.add_item(self.username_input)

    async def on_submit(self, interaction: discord.Interaction):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        username = self.username_input.value.strip()
        await interaction.response.defer(ephemeral=True)
        try:
            profile = await svc.link_roblox(self.guild_id, self.user_id, username)
        except Exception:
            profile = None
        if profile is None:
            return await interaction.followup.send(
                "Could not link that Roblox account. Please check the spelling and try again.",
                ephemeral=True,
            )
        await svc.repo.log_event(self.guild_id, self.user_id, "roblox_link",
                                 "roblox_id=" + str(profile.user_id))
        try:
            await svc.logging.emit(
                interaction.guild, "verification",
                title="Roblox account linked",
                color=0x5865F2,
                fields=[
                    ("Member", "<@" + str(self.user_id) + ">", True),
                    ("Roblox", profile.username or username, True),
                    ("Age (days)", str(profile.account_age_days or "unknown"), True),
                ],
            )
        except Exception:
            pass
        await interaction.followup.send(
            "Linked Roblox account: `" + (profile.username or username) + "`.",
            ephemeral=True,
        )


class VerifyPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Verification", style=discord.ButtonStyle.success,
                       custom_id="verify:start")
    async def start(self, interaction: discord.Interaction, _b: discord.ui.Button):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        sess = await svc.create_session(interaction.guild_id, interaction.user.id)
        if sess is None:
            return await interaction.response.send_message(
                "You are doing that too quickly. Please wait a moment.", ephemeral=True)
        embed = discord.Embed(title="Verification started",
                              description="Running security checks. This usually takes a few seconds.",
                              color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        try:
            verdict = await svc.verify(interaction.guild_id, interaction.user.id, sess.session_id)
        except Exception as exc:
            await interaction.followup.send(
                "Verification service is temporarily unavailable. Please try again shortly.",
                ephemeral=True)
            try:
                await svc.repo.log_event(interaction.guild_id, interaction.user.id,
                                         "verify_error", rex(exc))
            except Exception:
                pass
            return
        await _finish(interaction, svc, sess.session_id, verdict)

    @discord.ui.button(label="Link Roblox", style=discord.ButtonStyle.primary,
                       custom_id="verify:roblox")
    async def link_roblox(self, interaction: discord.Interaction, _b: discord.ui.Button):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        await interaction.response.send_modal(
            RobloxLinkModal(guild_id=interaction.guild_id, user_id=interaction.user.id))

    @discord.ui.button(label="I need help", style=discord.ButtonStyle.secondary,
                       custom_id="verify:help")
    async def help_btn(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await interaction.response.send_message(
            "If verification is not working, please open a support ticket.", ephemeral=True)


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
    verif_role = guild.get_role(int(verif_role_id)) if verif_role_id and verif_role_id.isdigit() else None
    quarantine_role = guild.get_role(int(quarantine_role_id)) if quarantine_role_id and quarantine_role_id.isdigit() else None

    sess = await svc.sessions.get(session_id)
    if sess is None:
        return

    base_fields = [
        ("Member", f"{member.mention} (`{member.id}`)", True),
        ("Risk score", f"`{verdict.risk_score}/100`", True),
        ("Risk level", f"`{verdict.risk_level.value}`", True),
        ("Confidence", f"`{verdict.confidence:.0%}`", True),
        ("Layer", f"`{int(verdict.required_layer.value)}`", True),
        ("Assessment ID", f"`{verdict.assessment_id or 0}`", True),
    ]
    signals = verdict.safe_reasons[:8]
    signals_text = "\n".join("- " + s for s in signals) if signals else "- No significant signals"
    if len(verdict.safe_reasons) > 8:
        signals_text += "\n- ... and " + str(len(verdict.safe_reasons) - 8) + " more"

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
            await svc.repo.save_session(sess)
        except Exception:
            pass
        try:
            await svc.logging.emit(guild, "verification", title="Verification Passed",
                                   color=0x57F287,
                                   fields=base_fields + [("Signals", signals_text, False),
                                                         ("Action", "Standard verification complete", True)])
        except Exception:
            pass
        embed = discord.Embed(title="Verified",
                              description="You now have access. Welcome aboard.",
                              color=0x57F287)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if verdict.risk_level.value in ("GUARDED", "ELEVATED", "HIGH"):
        try:
            sess.transition(VState.CHALLENGE_REQUIRED)
        except Exception:
            pass
        try:
            await svc.repo.save_session(sess)
            await svc.repo.record_attempt(gid, member.id, session_id, "PENDING_REVIEW", sess.layer)
        except Exception:
            pass
        try:
            await svc.logging.emit(guild, "verification", title="Verification - Enhanced Required",
                                   color=0xFEE75C,
                                   fields=base_fields + [("Signals", signals_text, False),
                                                         ("Action", "Member routed to enhanced verification", False),
                                                         ("Recommendation", verdict.recommendation, False)])
        except Exception:
            pass
        embed = discord.Embed(title="Additional verification required",
                              description=("Your account has been routed to enhanced verification. "
                                           "Please open a support ticket and mention this message so a "
                                           "moderator can assist."),
                              color=0xFEE75C)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

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
        await svc.repo.record_review(gid, member.id, sess.assessment_id, "QUARANTINE",
                                     svc.bot.user.id if svc.bot.user else 0, "Automatic quarantine")
        await svc.repo.save_session(sess)
    except Exception:
        pass
    try:
        await svc.logging.emit(guild, "verification", title="Verification - Quarantined",
                               color=0xED4245,
                               fields=base_fields + [("Signals", signals_text, False),
                                                     ("Action", "Member quarantined, pending moderator review", False),
                                                     ("Review", "Use /verify-review to approve, reject, or release", False)])
    except Exception:
        pass
    embed = discord.Embed(title="Manual review required",
                          description=("Your account has been placed in quarantine while a moderator "
                                       "reviews it. You will be notified once a decision has been made."),
                          color=0xED4245)
    await interaction.followup.send(embed=embed, ephemeral=True)


class ReviewView(discord.ui.View):
    def __init__(self, *, guild_id: int, user_id: int,
                 assessment_id, author_id: int):
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
            await svc.rate.hit("mod_action:g" + str(guild.id), limit=60, window_seconds=3600)
        except Exception:
            return await interaction.response.send_message("Too many actions this hour.", ephemeral=True)
        try:
            await svc.repo.record_review(guild.id, self.user_id, self.assessment_id,
                                         decision, interaction.user.id, "")
            await svc.repo.log_event(guild.id, self.user_id, "review",
                                     "decision=" + decision + " mod=" + str(interaction.user.id))
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
            await svc.logging.emit(guild, "verification",
                                    title="Verification Review - " + decision,
                                    color=color,
                                    fields=[("Member", "<@" + str(self.user_id) + "> (`" + str(self.user_id) + "`)", True),
                                            ("Moderator", interaction.user.mention, True),
                                            ("Decision", "`" + decision + "`", True),
                                            ("Assessment ID", "`" + str(self.assessment_id or 0) + "`", True)])
        except Exception:
            pass
        await interaction.response.send_message("Decision recorded: " + decision, ephemeral=True)

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

    @discord.ui.button(label="Reassess", style=discord.ButtonStyle.primary, row=1)
    async def reassess(self, interaction: discord.Interaction, _b: discord.ui.Button):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        guild = interaction.guild
        if guild is None:
            return
        try:
            await svc.rate.hit("reassess:g" + str(guild.id), limit=10, window_seconds=3600)
        except Exception:
            return await interaction.response.send_message("Too many reassessments this hour.", ephemeral=True)
        member = guild.get_member(self.user_id)
        if member is None:
            return await interaction.response.send_message("Member is not present.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            verdict = await svc.assess(member, "reassess", 0.0)
        except Exception:
            return await interaction.followup.send("Reassessment failed.", ephemeral=True)
        embed = discord.Embed(title="Reassessment - " + str(member), color=0x5865F2)
        embed.add_field(name="Risk score", value=str(verdict.risk_score) + "/100", inline=True)
        embed.add_field(name="Risk level", value=verdict.risk_level.value, inline=True)
        embed.add_field(name="Confidence", value=format(verdict.confidence, ".0%"), inline=True)
        embed.add_field(name="Layer", value=str(int(verdict.required_layer.value)), inline=True)
        embed.add_field(name="Assessment ID", value=str(verdict.assessment_id or 0), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="History", style=discord.ButtonStyle.secondary, row=1)
    async def history(self, interaction: discord.Interaction, _b: discord.ui.Button):
        svc: VerificationService = interaction.client.verification  # type: ignore[attr-defined]
        guild = interaction.guild
        if guild is None:
            return
        rows = await svc.repo.history_assessments(guild.id, self.user_id, limit=10)
        reviews = await svc.repo.list_reviews(guild.id, self.user_id, limit=10)
        embed = discord.Embed(title="History - <@" + str(self.user_id) + ">", color=0x5865F2)
        if not rows and not reviews:
            embed.description = "No history."
        for r in rows[:5]:
            embed.add_field(
                name="Assessment #" + str(r["id"]) + " (" + r["risk_level"] + ")",
                value="score=" + str(r["risk_score"]) + " conf=" + format(float(r["confidence"]), ".0%") +
                      " layer=" + str(r["required_layer"]),
                inline=False,
            )
        for rv in reviews[:5]:
            embed.add_field(
                name="Review #" + str(rv["id"]) + " - " + rv["decision"],
                value="mod=<@" + str(rv["moderator_id"]) + ">",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigService(bot.db)
        logging_svc = LoggingService(bot.db)
        self.service = VerificationService(
            bot=bot, db=bot.db, config_service=self.config, logging_service=logging_svc,
            session_timeout=int(os.getenv("VERIFY_SESSION_TIMEOUT", "900")),
        )
        bot.verification = self.service  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_view(VerifyPanelView())
        for guild in self.bot.guilds:
            try:
                await self.service.rebuild_fingerprint_index(guild.id)
            except Exception:
                pass
        try:
            now_wall = datetime.now(timezone.utc).timestamp()
            for guild in self.bot.guilds:
                rows = await self.service.repo.load_incomplete_sessions(guild.id)
                for r in rows:
                    try:
                        await self.service.sessions.restore(r, now_wall)
                    except Exception:
                        continue
        except Exception:
            pass
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        try:
            now = datetime.now(timezone.utc)
            age_days = max((now - member.created_at).days, 0)
            self.service.on_member_join(member, age_days)
            await self.service.record_rejoin_if_applicable(member)
            await self.service.save_member_history(member)

            row = await self.service.repo.latest_assessment(member.guild.id, member.id)
            if row and str(row["risk_level"]) == "CRITICAL":
                qid = await self.config.get(member.guild.id, "verify_quarantine_role_id")
                if qid and qid.isdigit():
                    qrole = member.guild.get_role(int(qid))
                    if qrole and qrole not in member.roles:
                        try:
                            await member.add_roles(qrole, reason="Prior CRITICAL assessment")
                        except discord.HTTPException:
                            pass
                        try:
                            await self.service.logging.emit(
                                member.guild, "verification",
                                title="Rejoin auto-quarantine",
                                color=0xED4245,
                                fields=[("Member", member.mention, True),
                                        ("Reason", "Prior CRITICAL risk level", False)],
                            )
                        except Exception:
                            pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            await self.service.on_member_leave(member)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        try:
            await self.service.on_member_ban(guild, user)
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

    @app_commands.command(name="verify", description="Start verification.")
    async def verify(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        sess = await self.service.create_session(interaction.guild_id, interaction.user.id)
        if sess is None:
            return await interaction.response.send_message("Too many attempts. Try again later.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            verdict = await self.service.verify(interaction.guild_id, interaction.user.id, sess.session_id)
        except Exception as exc:
            await interaction.followup.send("Verification service unavailable. Please try again.", ephemeral=True)
            try:
                await self.service.repo.log_event(interaction.guild_id, interaction.user.id,
                                                  "verify_error", rex(exc))
            except Exception:
                pass
            return
        await _finish(interaction, self.service, sess.session_id, verdict)

    @app_commands.command(name="verification-panel", description="Post the public verification panel.")
    @is_guild_admin()
    async def verification_panel(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Use in a text channel.", ephemeral=True)
        embed = discord.Embed(title="Verification",
                              description=("Press the button below to verify your account and gain access "
                                           "to the server."),
                              color=0x5865F2)
        await interaction.channel.send(embed=embed, view=VerifyPanelView())
        await interaction.response.send_message("Panel posted.", ephemeral=True)

    @app_commands.command(name="verify-roblox", description="Link your Roblox account.")
    async def verify_roblox(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        await interaction.response.send_modal(
            RobloxLinkModal(guild_id=interaction.guild_id, user_id=interaction.user.id))

    @app_commands.command(name="verify-roblox-status", description="Show your linked Roblox account.")
    async def verify_roblox_status(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return
        link = await self.service.repo.get_roblox_link(interaction.guild_id, interaction.user.id)
        if not link:
            return await interaction.response.send_message("No Roblox account linked.", ephemeral=True)
        embed = discord.Embed(title="Linked Roblox account", color=0x5865F2)
        embed.add_field(name="Roblox", value=str(link["roblox_name"]), inline=True)
        embed.add_field(name="Roblox ID", value=str(link["roblox_id"]), inline=True)
        embed.add_field(name="Linked at", value="<t:" + str(link["verified_at"]) + ":R>", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verify-unlink", description="Unlink your Roblox account.")
    async def verify_unlink(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return
        await self.service.repo.delete_roblox_link(interaction.guild_id, interaction.user.id)
        await self.service.repo.log_event(interaction.guild_id, interaction.user.id, "roblox_unlink", "")
        await interaction.response.send_message("Unlinked your Roblox account.", ephemeral=True)

    @app_commands.command(name="verify-status", description="Show the verification state for a member.")
    @is_moderator()
    async def verify_status(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild_id is None:
            return
        row = await self.service.repo.latest_assessment(interaction.guild_id, member.id)
        if not row:
            return await interaction.response.send_message("No assessment on record.", ephemeral=True)
        embed = discord.Embed(title="Verification status - " + str(member), color=0x5865F2)
        embed.add_field(name="Risk score", value=str(row["risk_score"]) + "/100", inline=True)
        embed.add_field(name="Risk level", value=str(row["risk_level"]), inline=True)
        embed.add_field(name="Confidence", value=format(float(row["confidence"]), ".0%"), inline=True)
        embed.add_field(name="Layer", value=str(row["required_layer"]), inline=True)
        embed.add_field(name="Recommendation", value=row["recommendation"] or "-", inline=False)
        if row["families_json"]:
            embed.add_field(name="Signal families", value=str(row["families_json"]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verify-review", description="Open a moderator review panel for a member.")
    @is_moderator()
    async def verify_review(self, interaction: discord.Interaction, member: discord.Member):
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
        view = ReviewView(guild_id=interaction.guild_id, user_id=member.id,
                          assessment_id=row["id"] if row else None,
                          author_id=interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="verify-false-positive", description="Mark the latest assessment as a false positive.")
    @is_moderator()
    async def verify_false_positive(self, interaction: discord.Interaction, member: discord.Member,
                                    reason: str = "moderator marked false positive"):
        if interaction.guild_id is None:
            return
        row = await self.service.repo.latest_assessment(interaction.guild_id, member.id)
        if not row:
            return await interaction.response.send_message("No assessment to correct.", ephemeral=True)
        await self.service.repo.record_review(
            interaction.guild_id, member.id, row["id"], "FALSE_POSITIVE",
            interaction.user.id, reason)
        await self.service.repo.log_event(
            interaction.guild_id, member.id, "false_positive",
            "assessment_id=" + str(row["id"]))
        await self.service.logging.emit(
            interaction.guild, "verification",
            title="Verification - False positive recorded",
            color=0x5865F2,
            fields=[("Member", member.mention, True),
                    ("Moderator", interaction.user.mention, True),
                    ("Assessment ID", "`" + str(row["id"]) + "`", True)])
        await interaction.response.send_message("Recorded as false positive.", ephemeral=True)

    @app_commands.command(name="verify-add-signature",
                          description="Add an abuse signature (avatar/name hash or username).")
    @is_guild_admin()
    async def verify_add_signature(self, interaction: discord.Interaction,
                                   key: str, value: str, weight: float = 1.0):
        if interaction.guild_id is None:
            return
        await self.service.repo.add_signature(interaction.guild_id, key, value.lower(), weight)
        await interaction.response.send_message("Signature added.", ephemeral=True)

    @app_commands.command(name="verify-remove-signature", description="Remove an abuse signature.")
    @is_guild_admin()
    async def verify_remove_signature(self, interaction: discord.Interaction,
                                      key: str, value: str):
        if interaction.guild_id is None:
            return
        n = await self.service.repo.remove_signature(interaction.guild_id, key, value.lower())
        await interaction.response.send_message("Removed " + str(n) + " signature(s).", ephemeral=True)

    @app_commands.command(name="verification-config", description="Configure the verification system.")
    @is_guild_admin()
    async def verification_config(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if gid is None:
            return
        embed = discord.Embed(title="Verification configuration", color=0x5865F2)
        for label, key in [("Verification role", "verify_role_id"),
                           ("Quarantine role", "verify_quarantine_role_id"),
                           ("Log channel", "verify_log_channel_id")]:
            raw = await self.config.get(gid, key)
            shown = "not set"
            if raw and raw.isdigit() and interaction.guild:
                obj = interaction.guild.get_role(int(raw)) or interaction.guild.get_channel(int(raw))
                if obj is not None:
                    shown = obj.mention
            embed.add_field(name=label, value=shown, inline=True)
        embed.set_footer(text="Use the commands below to configure.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verification-role", description="Set the role given on successful verification.")
    @is_guild_admin()
    async def verification_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.config.set(interaction.guild_id, "verify_role_id", role.id)
        await interaction.response.send_message("Verification role set to " + role.mention + ".", ephemeral=True)

    @app_commands.command(name="verification-quarantine-role", description="Set the quarantine role.")
    @is_guild_admin()
    async def verification_quarantine_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.config.set(interaction.guild_id, "verify_quarantine_role_id", role.id)
        await interaction.response.send_message("Quarantine role set to " + role.mention + ".", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
