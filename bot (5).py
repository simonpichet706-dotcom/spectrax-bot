# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║      BOT DISCORD - SpectraX X Mln AI - GÉNÉRATEUR DE CODE VERSE UEFN     ║
# ╠═══════════════════════════════════════════════════════════════════════════╣
# ║  INSTALLATION :  pip install discord.py groq flask flask-cors aiohttp     ║
# ║  LANCEMENT    :  python bot.py                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import discord
from discord.ui import View, Button
from groq import Groq
import datetime
import threading
import re
import asyncio
import os
import sys
import logging
import random
import string
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

# ════════════════════════════════════════════════════════════════════════════
#  📋  SYSTÈME DE LOGS
# ════════════════════════════════════════════════════════════════════════════

LOG_FILE = "bot.log"

# Formatter coloré pour la console
class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[94m",   # Bleu
        "INFO":     "\033[92m",   # Vert
        "WARNING":  "\033[93m",   # Jaune
        "ERROR":    "\033[91m",   # Rouge
        "CRITICAL": "\033[95m",   # Magenta
    }
    RESET = "\033[0m"
    BOLD  = "\033[1m"

    def format(self, record):
        color  = self.COLORS.get(record.levelname, self.RESET)
        time   = datetime.datetime.now().strftime("%d/%m %H:%M:%S")
        level  = f"{color}{self.BOLD}[{record.levelname}]{self.RESET}"
        return f"{color}[{time}]{self.RESET} {level} {record.getMessage()}"

# Formatter plat pour le fichier
file_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)

logger = logging.getLogger("SpectraX")
logger.setLevel(logging.DEBUG)

# Handler console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(ColorFormatter())

# Handler fichier tournant (max 5 Mo, 3 fichiers de backup)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# ════════════════════════════════════════════════════════════════════════════
#  🔧  CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

DISCORD_TOKEN    = os.environ.get("DISCORD_TOKEN")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")

# Serveur requis pour utiliser le bot (génération de code)
REQUIRED_GUILD_ID   = 1342552835232891023
INVITE_LINK         = "https://discord.gg/G2wxH4FC5S"

# Serveur où +createmenu fonctionne + statut requis pour l'accès
MENU_GUILD_ID       = 1500173737801289748
REQUIRED_STATUS     = ".gg/uwr44JEW"

# Salon où tout le monde peut faire +invites (et seule cette commande est autorisée)
INVITES_CHANNEL_ID  = 1500189261314396211

# ID créateur principal (seul à pouvoir faire +createmenu)
OWNER_ID = 1340039953635086438

# IDs créateurs (peuvent utiliser les commandes +)
CREATOR_IDS = {
    1340039953635086438,
    1099122712477184091,
}

DASHBOARD_PORT = 5000

# Rôle attribué après vérification captcha
VERIFY_ROLE_ID = 1500174233051861306

# Sessions captcha en cours { user_id: "CODE" }
captcha_sessions: dict = {}

AI_NAME    = "SpectraX AI"
AI_EMOJI   = "🌌"
BOT_COLOR  = 0x5865F2
OK_COLOR   = 0x57F287
ERR_COLOR  = 0xED4245
PURPLE     = 0x9B59B6
GOLD_COLOR = 0xF1C40F

# État du bot (géré par les créateurs)
bot_enabled = True

stats = {
    "total_generations": 0,
    "total_errors": 0,
    "bot_status": "démarrage...",
    "bot_name": "",
    "last_requests": [],
    "logs": [],
    "start_time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
}

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members  = True
intents.presences = True   # ← nécessaire pour lire les statuts/activités
intents.moderation = True  # ← nécessaire pour les events ban/unban
bot = discord.Client(intents=intents)
client_groq = Groq(api_key=GROQ_API_KEY)

# ════════════════════════════════════════════════════════════════════════════
#  STOCKAGE ACCÈS ACCORDÉS (en mémoire — persistant tant que le bot tourne)
#  Pour une persistance totale entre redémarrages, utiliser un fichier JSON.
# ════════════════════════════════════════════════════════════════════════════

# Set des user_id qui ont eu l'accès validé
verified_users: set = set()

# ════════════════════════════════════════════════════════════════════════════
#  🛡️  SYSTÈME DE LOGS DISCORD  (+logon)
# ════════════════════════════════════════════════════════════════════════════

# Rôle "quarantaine" attribué en cas d'infraction
QUARANTINE_ROLE_ID = 1500174233051861306

# Noms des salons de logs (créés automatiquement par +logon)
LOG_CHANNELS = {
    "messages":  "📝┃logs-messages",
    "sanctions": "🔨┃logs-sanctions",
    "salons":    "🏗️┃logs-salons",
    "roles":     "🎭┃logs-roles",
    "snapshot":  "📸┃logs-snapshot",
}
LOG_CATEGORY_NAME = "📋 LOGS SPECTRAX"

# Stockage des IDs de salons de logs par guilde  { guild_id: { "messages": channel_id, ... } }
log_channels_ids: dict = {}

# ── Anti-raid : suivi des modifications récentes ──────────────────────────
# { guild_id: { user_id: [timestamp, ...] } }
channel_mod_tracker: dict = {}   # modifications de salons
ban_tracker: dict         = {}   # bans récents  { guild_id: [timestamp, ...] }

CHANNEL_MOD_LIMIT  = 3    # max modifications de salon en ...
CHANNEL_MOD_WINDOW = 30   # ... secondes
BAN_LIMIT          = 5    # max bans en ...
BAN_WINDOW         = 60   # ... secondes

# Snapshot des salons/catégories pour la restauration automatique
# { guild_id: { channel_id: { name, type, category_id, position, overwrites_json } } }
guild_snapshot: dict = {}


# ─── Helpers logs ─────────────────────────────────────────────────────────

def get_log_channel_id(guild_id: int, key: str) -> int | None:
    return log_channels_ids.get(guild_id, {}).get(key)

async def send_log(guild: discord.Guild, key: str, embed: discord.Embed):
    """Envoie un embed dans le salon de log correspondant."""
    cid = get_log_channel_id(guild.id, key)
    if not cid:
        return
    ch = guild.get_channel(cid)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def now_str() -> str:
    return datetime.datetime.now().strftime("%d/%m/%Y à %H:%M:%S")

def snapshot_guild(guild: discord.Guild):
    """Enregistre l'état actuel des salons et catégories du serveur."""
    snap = {}
    for ch in guild.channels:
        try:
            overwrites_data = {}
            for target, overwrite in ch.overwrites.items():
                key_str = f"{'role' if isinstance(target, discord.Role) else 'member'}:{target.id}"
                allow, deny = overwrite.pair()
                overwrites_data[key_str] = {"allow": allow.value, "deny": deny.value}
            snap[ch.id] = {
                "name":        ch.name,
                "type":        str(ch.type),
                "category_id": ch.category_id,
                "position":    ch.position,
                "overwrites":  overwrites_data,
                "topic":       getattr(ch, "topic", None),
                "nsfw":        getattr(ch, "nsfw", False),
            }
        except Exception:
            pass
    guild_snapshot[guild.id] = snap
    logger.info(f"[SNAPSHOT] Serveur '{guild.name}' — {len(snap)} salons enregistrés")

async def restore_channel(guild: discord.Guild, channel_id: int, restored_by: str = "auto") -> bool:
    """Tente de restaurer un salon supprimé/modifié à partir du snapshot."""
    snap = guild_snapshot.get(guild.id, {}).get(channel_id)
    if not snap:
        return False
    # Retrouver la catégorie si nécessaire
    category = None
    if snap["category_id"]:
        category = guild.get_channel(snap["category_id"])

    ch_type = snap["type"]
    try:
        if ch_type == "ChannelType.text":
            new_ch = await guild.create_text_channel(
                snap["name"], category=category,
                topic=snap.get("topic"), nsfw=snap.get("nsfw", False),
                reason=f"Restauration automatique par SpectraX ({restored_by})"
            )
        elif ch_type == "ChannelType.voice":
            new_ch = await guild.create_voice_channel(
                snap["name"], category=category,
                reason=f"Restauration automatique par SpectraX ({restored_by})"
            )
        else:
            return False

        # Remettre les permissions
        for key_str, perm_data in snap["overwrites"].items():
            target_type, target_id = key_str.split(":")
            target_id = int(target_id)
            if target_type == "role":
                target = guild.get_role(target_id)
            else:
                target = guild.get_member(target_id)
            if target:
                ow = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(perm_data["allow"]),
                    discord.Permissions(perm_data["deny"])
                )
                await new_ch.set_permissions(target, overwrite=ow)

        logger.info(f"[RESTORE] Salon #{snap['name']} restauré sur '{guild.name}'")
        return True
    except Exception as e:
        logger.error(f"[RESTORE] Échec restauration salon {channel_id}: {e}")
        return False


# ─── Quarantaine ──────────────────────────────────────────────────────────

async def quarantine_member(guild: discord.Guild, member: discord.Member | None,
                             reason: str, log_key: str):
    """
    Retire tous les rôles d'un membre et lui attribue le rôle quarantaine.
    Prévient le créateur par DM et log l'action.
    """
    if member is None:
        return

    quarantine_role = guild.get_role(QUARANTINE_ROLE_ID)
    if quarantine_role is None:
        logger.warning(f"[QUARANTINE] Rôle quarantaine {QUARANTINE_ROLE_ID} introuvable sur '{guild.name}'")
        return

    old_roles = [r for r in member.roles if not r.is_default()]
    try:
        await member.edit(roles=[quarantine_role], reason=f"Quarantaine auto — {reason}")
        logger.warning(f"[QUARANTINE] {member} mis en quarantaine sur '{guild.name}' — {reason}")
    except Exception as e:
        logger.error(f"[QUARANTINE] Impossible de mettre {member} en quarantaine: {e}")
        return

    # ── Log dans le salon correspondant
    embed_log = discord.Embed(color=0xFF0000, title="🚨 QUARANTAINE AUTOMATIQUE")
    embed_log.add_field(name="👤 Membre",    value=f"{member.mention} (`{member}`)", inline=True)
    embed_log.add_field(name="⚠️ Raison",    value=reason, inline=True)
    embed_log.add_field(name="🗑️ Rôles retirés", value=", ".join(r.mention for r in old_roles) or "Aucun", inline=False)
    embed_log.add_field(name="🔒 Rôle attribué", value=quarantine_role.mention, inline=True)
    embed_log.add_field(name="🕐 Date",      value=now_str(), inline=True)
    embed_log.set_footer(text=f"SpectraX Protection — {guild.name}")
    await send_log(guild, log_key, embed_log)

    # ── DM au créateur
    owner = bot.get_user(OWNER_ID)
    if owner:
        try:
            dm_embed = discord.Embed(color=0xFF0000, title="🚨 ALERTE — Quarantaine automatique")
            dm_embed.add_field(name="🏠 Serveur", value=f"`{guild.name}`", inline=True)
            dm_embed.add_field(name="👤 Membre",  value=f"`{member}` ({member.id})", inline=True)
            dm_embed.add_field(name="⚠️ Raison",  value=reason, inline=False)
            dm_embed.add_field(name="🗑️ Rôles retirés", value=", ".join(r.name for r in old_roles) or "Aucun", inline=False)
            dm_embed.add_field(name="🕐 Date",    value=now_str(), inline=True)
            await owner.send(embed=dm_embed)
        except Exception:
            pass


# ─── Snapshot automatique toutes les 2 minutes ────────────────────────────

async def auto_snapshot_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            if guild.id in log_channels_ids:   # seulement les serveurs avec logs activés
                old_snap = guild_snapshot.get(guild.id, {})
                current_channel_ids = {ch.id for ch in guild.channels}

                # ── Vérifier les salons disparus depuis le dernier snapshot et les restaurer
                restored_list = []
                for ch_id, ch_data in old_snap.items():
                    if ch_id not in current_channel_ids:
                        # Ce salon a disparu — on le restaure
                        restored = await restore_channel(guild, ch_id, restored_by="snapshot auto")
                        if restored:
                            restored_list.append(ch_data["name"])
                            logger.warning(f"[SNAPSHOT RESTORE] #{ch_data['name']} restauré sur '{guild.name}'")

                # Prendre un nouveau snapshot après restaurations
                snapshot_guild(guild)
                snap = guild_snapshot.get(guild.id, {})
                categories = [c for c in guild.categories]
                ch_text    = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
                ch_voice   = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])

                color = 0x57F287 if restored_list else 0x5865F2
                desc  = (
                    f"**Salons textuels :** {ch_text}\n"
                    f"**Salons vocaux :** {ch_voice}\n"
                    f"**Catégories :** {len(categories)}\n"
                    f"**Total enregistré :** {len(snap)} salons\n"
                )
                if restored_list:
                    desc += f"\n🔄 **Salons restaurés ({len(restored_list)}) :**\n"
                    desc += "\n".join(f"• `#{n}`" for n in restored_list)

                desc += f"\n\n🕐 `{now_str()}`"

                embed = discord.Embed(color=color, title="📸 Snapshot automatique")
                embed.description = desc
                if restored_list:
                    embed.title = "📸 Snapshot + Restauration automatique"
                embed.set_footer(text="SpectraX Logs — snapshot toutes les 2 min")
                await send_log(guild, "snapshot", embed)

                # DM créateur si des salons ont été restaurés
                if restored_list:
                    owner = bot.get_user(OWNER_ID)
                    if owner:
                        try:
                            dm = discord.Embed(color=0x57F287, title="🔄 Restauration automatique — Snapshot")
                            dm.add_field(name="🏠 Serveur",          value=f"`{guild.name}`", inline=True)
                            dm.add_field(name="🔄 Salons restaurés", value="\n".join(f"• `#{n}`" for n in restored_list), inline=False)
                            dm.add_field(name="🕐 Date",             value=now_str(), inline=True)
                            dm.add_field(name="⚙️ Par",              value="SpectraX Snapshot Auto", inline=True)
                            await owner.send(embed=dm)
                        except Exception:
                            pass

        await asyncio.sleep(120)  # 2 minutes


# ─── Création automatique des salons de logs ──────────────────────────────

async def setup_log_channels(guild: discord.Guild) -> dict:
    """Crée la catégorie et les salons de logs si absents. Retourne le dict des IDs."""
    # Chercher ou créer la catégorie
    category = discord.utils.get(guild.categories, name=LOG_CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(
            LOG_CATEGORY_NAME,
            reason="SpectraX — création automatique des logs"
        )
        logger.info(f"[LOGON] Catégorie '{LOG_CATEGORY_NAME}' créée sur '{guild.name}'")

    # Permissions : seuls les créateurs (et le bot) voient la catégorie
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    # Donner accès aux membres créateurs
    for cid in CREATOR_IDS:
        m = guild.get_member(cid)
        if m:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

    channels_map = {}
    for key, name in LOG_CHANNELS.items():
        existing = discord.utils.get(guild.text_channels, name=name)
        if existing is None:
            ch = await guild.create_text_channel(
                name, category=category,
                overwrites=overwrites,
                topic=f"Logs automatiques SpectraX — {key}",
                reason="SpectraX — setup logs"
            )
            logger.info(f"[LOGON] Salon '{name}' créé")
        else:
            ch = existing
        channels_map[key] = ch.id

    log_channels_ids[guild.id] = channels_map
    snapshot_guild(guild)
    return channels_map


# ════════════════════════════════════════════════════════════════════════════
#  UTILS
# ════════════════════════════════════════════════════════════════════════════

def is_creator(user_id: int) -> bool:
    return user_id in CREATOR_IDS

async def is_member_of_required_guild(user_id: int) -> bool:
    """Vérifie si l'utilisateur est membre du serveur requis (pour le bot IA)."""
    guild = bot.get_guild(REQUIRED_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(REQUIRED_GUILD_ID)
        except Exception:
            return False
    try:
        member = guild.get_member(user_id)
        if member:
            return True
        member = await guild.fetch_member(user_id)
        return member is not None
    except discord.NotFound:
        return False
    except Exception:
        return False

def has_required_status(member: discord.Member) -> bool:
    """Vérifie si le membre a le statut requis (.gg/uwr44JEW) dans ses activités."""
    if member is None:
        return False
    for activity in member.activities:
        # Statut custom (le petit texte que les gens mettent sous leur pseudo)
        if isinstance(activity, discord.CustomActivity):
            if activity.name and REQUIRED_STATUS.lower() in activity.name.lower():
                return True
        # Vérif aussi dans tous les autres types d'activité (streaming, playing...)
        if hasattr(activity, 'name') and activity.name:
            if REQUIRED_STATUS.lower() in activity.name.lower():
                return True
        if hasattr(activity, 'state') and activity.state:
            if REQUIRED_STATUS.lower() in activity.state.lower():
                return True
        if hasattr(activity, 'details') and activity.details:
            if REQUIRED_STATUS.lower() in activity.details.lower():
                return True
    return False

async def has_invited_someone(member: discord.Member) -> bool:
    """Vérifie si le membre a invité au moins 5 personnes qui ont rejoint le serveur."""
    guild = member.guild
    total_uses = 0
    try:
        invites = await guild.invites()
        for invite in invites:
            if invite.inviter and invite.inviter.id == member.id and invite.uses:
                total_uses += invite.uses
        return total_uses >= 5
    except Exception:
        pass
    return False

async def check_access_conditions(member: discord.Member) -> dict:
    """
    Vérifie les 3 conditions d'accès :
    1. Être membre du serveur (déjà garanti si on a le member object)
    2. Avoir le statut requis dans son profil
    3. Avoir invité au moins 5 personnes

    Retourne un dict avec les résultats et si l'accès global est accordé.
    """
    status_ok  = has_required_status(member)
    invite_ok  = await has_invited_someone(member)

    return {
        "status_ok": status_ok,
        "invite_ok": invite_ok,
        "all_ok":    status_ok and invite_ok,
    }

async def revoke_if_conditions_lost(member: discord.Member):
    """
    Si un utilisateur vérifié a perdu son statut OU a quitté le serveur requis,
    on révoque son accès.
    """
    if member.id not in verified_users:
        return
    status_ok = has_required_status(member)
    if not status_ok:
        verified_users.discard(member.id)

def log_request(user: str, feature: str, success: bool):
    stats["last_requests"].insert(0, {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "user": user, "feature": feature[:60], "success": success,
    })
    stats["last_requests"] = stats["last_requests"][:20]
    if success: stats["total_generations"] += 1
    else:       stats["total_errors"]      += 1

def ask_groq(prompt: str) -> str:
    r = client_groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es SpectraX AI, un expert UEFN et Verse intégré dans un bot Discord. "
                    "Tu génères du code Verse professionnel, moderne et fonctionnel. "
                    "Ne mentionne jamais Groq, LLaMA, Meta ou tout autre technologie sous-jacente. "
                    "Tu es simplement SpectraX AI."
                )
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=4000,
    )
    return r.choices[0].message.content

def build_prompt(reponses: dict) -> str:
    nom        = reponses.get("nom_projet", "Projet UEFN")
    desc       = reponses.get("description", "")
    type_jeu   = reponses.get("type_jeu", "")
    nb_joueurs = reponses.get("nb_joueurs", "")
    devices    = reponses.get("devices", "")
    hud        = reponses.get("hud", "")
    score      = reponses.get("score", "")
    timer      = reponses.get("timer", "")
    equipes    = reponses.get("equipes", "")
    respawn    = reponses.get("respawn", "")
    items      = reponses.get("items", "")
    triggers   = reponses.get("triggers", "")
    son        = reponses.get("son", "")
    npc        = reponses.get("npc", "")
    zones      = reponses.get("zones", "")
    conditions = reponses.get("conditions_victoire", "")
    inventaire = reponses.get("inventaire", "")
    erreurs    = reponses.get("erreurs", "")
    extras     = reponses.get("extras", "")
    niveau     = reponses.get("niveau", "intermédiaire")

    return f"""Tu es SpectraX AI, expert UEFN et Verse. Génère un code Verse COMPLET, PROFESSIONNEL et FONCTIONNEL.

PROJET : {nom}
DESCRIPTION : {desc}
TYPE DE JEU : {type_jeu}
NOMBRE DE JOUEURS : {nb_joueurs}
NIVEAU DU DÉVELOPPEUR : {niveau}

FEATURES DEMANDÉES :
- HUD / Affichage : {hud}
- Système de score : {score}
- Chrono / Timer : {timer}
- Équipes : {equipes}
- Respawn : {respawn}
- Items / Objets : {items}
- Triggers / Zones : {triggers}
- Sons / Effets : {son}
- NPC / Gardiens : {npc}
- Zones spéciales : {zones}
- Conditions de victoire : {conditions}
- Inventaire : {inventaire}
- Devices UEFN utilisés : {devices}
- Erreurs à corriger : {erreurs}
- Extras / Autres : {extras}

RÈGLES ABSOLUES DE FORMAT :
1. Commence par une explication claire (5-8 lignes) de ce que fait le code
2. Ensuite le code Verse ENTIER dans UN SEUL bloc ```verse ... ```
3. Le code DOIT commencer par les imports : using {{ /Fortnite.com/... }} etc.
4. Utilise @editable sur les variables configurables dans UEFN
5. Ajoute des commentaires clairs sur chaque section
6. Le code doit être syntaxiquement correct et complet
7. Après le code, liste les points clés (5-8 bullet points)
8. Termine par les instructions de connexion dans UEFN

EXEMPLE DE STRUCTURE VERSE ATTENDUE :
```verse
using {{ /Fortnite.com/Devices }}
using {{ /Fortnite.com/Characters }}
using {{ /Fortnite.com/Teams }}
using {{ /UnrealEngine.com/Temporary/Diagnostics }}
using {{ /UnrealEngine.com/Temporary/SpatialMath }}
using {{ /Verse.org/Simulation }}

# Ton device principal hérite de creative_device
nom_device<public> := class(creative_device):

    # Variables @editable (configurables dans UEFN)
    @editable
    MaVariable : int = 0

    # Fonction appelée au démarrage
    OnBegin<override>()<suspends> : void =
        # Logique ici
        ...
```

Génère maintenant le code complet pour ce projet."""


def split_response(text: str) -> list:
    parts = re.split(r"(```[\s\S]*?```)", text)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("```"):
            part = re.sub(r"^```[a-zA-Z]*", "```verse", part)
            if len(part) > 1990:
                lines = part.split("\n")
                chunk = ""
                for line in lines:
                    if len(chunk) + len(line) + 1 > 1985:
                        result.append(chunk + "\n```")
                        chunk = "```verse\n" + line
                    else:
                        chunk += ("\n" if chunk else "") + line
                if chunk:
                    if not chunk.endswith("```"):
                        chunk += "\n```"
                    result.append(chunk)
            else:
                result.append(part)
        else:
            while len(part) > 1900:
                result.append(part[:1900])
                part = part[1900:]
            if part:
                result.append(part)
    return result

# ════════════════════════════════════════════════════════════════════════════
#  SESSIONS
# ════════════════════════════════════════════════════════════════════════════

sessions: dict = {}

# ════════════════════════════════════════════════════════════════════════════
#  MODALS (formulaires en 4 parties de 5 champs)
# ════════════════════════════════════════════════════════════════════════════

class FormulaireModal1(discord.ui.Modal, title="🌌 Partie 1/4 — Projet & Base"):
    nom_projet  = discord.ui.TextInput(label="📛 Nom du projet", placeholder="Ex: ZoneWars Pro, BattleRoyale Custom...", required=True, max_length=100)
    description = discord.ui.TextInput(label="📋 Description complète", style=discord.TextStyle.paragraph, placeholder="Décris en détail ce que tu veux créer...", required=True, min_length=20, max_length=500)
    type_jeu    = discord.ui.TextInput(label="🎮 Type de jeu", placeholder="Ex: Battle Royale, Zone Wars, Course, Escape Game...", required=True, max_length=100)
    nb_joueurs  = discord.ui.TextInput(label="👥 Nombre de joueurs", placeholder="Ex: 1-16, solo, duos, 4 équipes de 4...", required=True, max_length=50)
    niveau      = discord.ui.TextInput(label="📊 Ton niveau en Verse", placeholder="débutant / intermédiaire / avancé", required=True, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid not in sessions:
            sessions[uid] = {}
        sessions[uid].update({
            "nom_projet":  self.nom_projet.value,
            "description": self.description.value,
            "type_jeu":    self.type_jeu.value,
            "nb_joueurs":  self.nb_joueurs.value,
            "niveau":      self.niveau.value,
        })
        embed = discord.Embed(color=PURPLE)
        embed.set_author(name=f"{AI_EMOJI} {AI_NAME} — Partie 2/4")
        embed.description = "✅ Partie 1 enregistrée !\n\nClique pour remplir la **partie 2** sur les systèmes de jeu."
        embed.set_footer(text=f"2/4  •  {AI_NAME}")
        await interaction.response.send_message(embed=embed, view=FormulaireView2(uid), ephemeral=True)


class FormulaireModal2(discord.ui.Modal, title="🎯 Partie 2/4 — Systèmes de jeu"):
    hud    = discord.ui.TextInput(label="🖥️ HUD / Affichage écran", placeholder="Ex: Score en haut, timer en bas, vie sur le côté... ou 'Aucun'", required=True, max_length=200)
    score  = discord.ui.TextInput(label="🏆 Système de score", placeholder="Ex: +1 par kill, score d'équipe, top 1 = victoire... ou 'Aucun'", required=True, max_length=200)
    timer  = discord.ui.TextInput(label="⏱️ Chrono / Timer", placeholder="Ex: 5 min de jeu, compte à rebours, round de 3 min... ou 'Aucun'", required=True, max_length=200)
    equipes = discord.ui.TextInput(label="👥 Équipes", placeholder="Ex: 2 équipes Rouge/Bleu, 4 équipes, solo FFA... ou 'Aucun'", required=True, max_length=200)
    respawn = discord.ui.TextInput(label="💀 Système de respawn", placeholder="Ex: Respawn auto après 5s, 3 vies max, pas de respawn... ou 'Aucun'", required=True, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        sessions[uid].update({
            "hud":    self.hud.value,
            "score":  self.score.value,
            "timer":  self.timer.value,
            "equipes": self.equipes.value,
            "respawn": self.respawn.value,
        })
        embed = discord.Embed(color=PURPLE)
        embed.set_author(name=f"{AI_EMOJI} {AI_NAME} — Partie 3/4")
        embed.description = "✅ Partie 2 enregistrée !\n\nClique pour remplir la **partie 3** sur les éléments interactifs."
        embed.set_footer(text=f"3/4  •  {AI_NAME}")
        await interaction.response.send_message(embed=embed, view=FormulaireView3(uid), ephemeral=True)


class FormulaireModal3(discord.ui.Modal, title="⚡ Partie 3/4 — Éléments interactifs"):
    items    = discord.ui.TextInput(label="🎒 Items / Objets", placeholder="Ex: Coffres avec armes aléatoires, heal items... ou 'Aucun'", required=True, max_length=200)
    triggers = discord.ui.TextInput(label="⚡ Triggers / Zones", placeholder="Ex: Zone qui inflige des dégâts, trigger au sol... ou 'Aucun'", required=True, max_length=200)
    son      = discord.ui.TextInput(label="🔊 Sons / Effets visuels", placeholder="Ex: Son à chaque kill, explosion visuelle... ou 'Aucun'", required=True, max_length=200)
    npc      = discord.ui.TextInput(label="🤖 NPC / Gardiens", placeholder="Ex: Gardes qui patrouillent, boss final... ou 'Aucun'", required=True, max_length=200)
    zones    = discord.ui.TextInput(label="🗺️ Zones spéciales", placeholder="Ex: Zone safe, zone de dégâts, zone de spawn... ou 'Aucun'", required=True, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        sessions[uid].update({
            "items":    self.items.value,
            "triggers": self.triggers.value,
            "son":      self.son.value,
            "npc":      self.npc.value,
            "zones":    self.zones.value,
        })
        embed = discord.Embed(color=PURPLE)
        embed.set_author(name=f"{AI_EMOJI} {AI_NAME} — Partie 4/4")
        embed.description = "✅ Partie 3 enregistrée !\n\nClique pour remplir la **partie 4** — dernière étape !"
        embed.set_footer(text=f"4/4  •  {AI_NAME}")
        await interaction.response.send_message(embed=embed, view=FormulaireView4(uid), ephemeral=True)


class FormulaireModal4(discord.ui.Modal, title="🏁 Partie 4/4 — Finitions"):
    conditions = discord.ui.TextInput(label="🏆 Conditions de victoire", placeholder="Ex: Premier à 20 kills, dernier survivant, capturer 3 zones...", required=True, max_length=200)
    inventaire = discord.ui.TextInput(label="🎒 Inventaire / Armes", placeholder="Ex: AK + Shotgun au spawn, inventaire vide, armes custom... ou 'Aucun'", required=True, max_length=200)
    devices    = discord.ui.TextInput(label="🧩 Devices UEFN utilisés", placeholder="Ex: trigger_device, hud_message_device, team_settings... ou 'Je sais pas'", required=True, max_length=200)
    erreurs    = discord.ui.TextInput(label="🐛 Erreurs à corriger", style=discord.TextStyle.paragraph, placeholder="Colle ton code bugué ici si tu veux que je le corrige... ou 'Aucune'", required=True, max_length=500)
    extras     = discord.ui.TextInput(label="✨ Extras / Autres", placeholder="Tout ce que tu n'as pas pu mettre avant... ou 'Rien'", required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        sessions[uid].update({
            "conditions_victoire": self.conditions.value,
            "inventaire":          self.inventaire.value,
            "devices":             self.devices.value,
            "erreurs":             self.erreurs.value,
            "extras":              self.extras.value or "Rien",
        })
        await generer_code(interaction, uid)


# ════════════════════════════════════════════════════════════════════════════
#  VUES (boutons pour ouvrir les modals)
# ════════════════════════════════════════════════════════════════════════════

class FormulaireView2(View):
    def __init__(self, uid): super().__init__(timeout=300); self.uid = uid
    @discord.ui.button(label="Remplir la partie 2 →", style=discord.ButtonStyle.blurple, emoji="🎯")
    async def btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Pas ton formulaire !", ephemeral=True); return
        await interaction.response.send_modal(FormulaireModal2())

class FormulaireView3(View):
    def __init__(self, uid): super().__init__(timeout=300); self.uid = uid
    @discord.ui.button(label="Remplir la partie 3 →", style=discord.ButtonStyle.blurple, emoji="⚡")
    async def btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Pas ton formulaire !", ephemeral=True); return
        await interaction.response.send_modal(FormulaireModal3())

class FormulaireView4(View):
    def __init__(self, uid): super().__init__(timeout=300); self.uid = uid
    @discord.ui.button(label="Remplir la partie 4 →", style=discord.ButtonStyle.success, emoji="🏁")
    async def btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Pas ton formulaire !", ephemeral=True); return
        await interaction.response.send_modal(FormulaireModal4())


# ════════════════════════════════════════════════════════════════════════════
#  GÉNÉRATION DU CODE
# ════════════════════════════════════════════════════════════════════════════

async def generer_code(interaction: discord.Interaction, user_id: int):
    session = sessions.get(user_id, {})

    embed_load = discord.Embed(color=BOT_COLOR)
    embed_load.set_author(name=f"{AI_EMOJI} {AI_NAME} — Génération en cours...")
    embed_load.description = (
        "⚙️ Analyse de tes réponses...\n"
        "🧠 Génération du code Verse en cours...\n"
        "> *Quelques secondes, le code sera complet et fonctionnel !*"
    )
    await interaction.response.send_message(embed=embed_load, ephemeral=True)

    try:
        loop   = asyncio.get_event_loop()
        prompt = build_prompt(session)
        reponse = await loop.run_in_executor(None, ask_groq, prompt)

        log_request(interaction.user.display_name, session.get("nom_projet", "?"), True)

        embed_recap = discord.Embed(color=OK_COLOR)
        embed_recap.set_author(name="🎉  Ton code Verse est prêt !")
        embed_recap.add_field(name="📛  Projet",   value=f"`{session.get('nom_projet','?')}`",  inline=True)
        embed_recap.add_field(name="🎮  Type",     value=f"`{session.get('type_jeu','?')}`",    inline=True)
        embed_recap.add_field(name="📊  Niveau",   value=f"`{session.get('niveau','?')}`",      inline=True)
        embed_recap.add_field(name="🔒  Visibilité", value="`Visible uniquement par toi`",       inline=False)
        embed_recap.set_footer(text=f"{AI_EMOJI} {AI_NAME}  •  {datetime.datetime.now().strftime('%H:%M:%S')}")
        await interaction.followup.send(embed=embed_recap, ephemeral=True)

        for chunk in split_response(reponse):
            await interaction.followup.send(chunk, ephemeral=True)

        embed_tips = discord.Embed(color=PURPLE)
        embed_tips.set_author(name="💡 Comment utiliser ton code")
        embed_tips.add_field(name="📋  Copier",     value="Clique le bouton 📋 en haut à droite du bloc de code", inline=False)
        embed_tips.add_field(name="🛠️  Compiler",   value="Appuie sur `Ctrl + B` dans UEFN pour vérifier le code", inline=False)
        embed_tips.add_field(name="🔧  @editable",  value="Les variables `@editable` sont modifiables directement dans UEFN sans toucher au code", inline=False)
        embed_tips.add_field(name="🐛  Bug ?",      value="Retape `hey vs` et colle ton erreur dans le champ prévu !", inline=False)
        embed_tips.add_field(name="📖  Doc Verse",  value="[Documentation officielle ↗](https://dev.epicgames.com/documentation/verse)", inline=False)
        embed_tips.set_footer(text=f"Merci d'utiliser {AI_NAME} {AI_EMOJI}")
        await interaction.followup.send(embed=embed_tips, ephemeral=True)

    except Exception as error:
        log_request(interaction.user.display_name, session.get("nom_projet", "?"), False)
        print(f"Erreur : {error}")
        await interaction.followup.send(
            embed=discord.Embed(title="❌ Erreur", description=f"```{str(error)[:300]}```", color=ERR_COLOR),
            ephemeral=True,
        )
    finally:
        sessions.pop(user_id, None)


# ════════════════════════════════════════════════════════════════════════════
#  BOUTON DÉMARRER (génération IA)
# ════════════════════════════════════════════════════════════════════════════

class StartView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="  Générer mon code Verse", style=discord.ButtonStyle.blurple, emoji="⚡", custom_id="spectrax_start_v5")
    async def start(self, interaction: discord.Interaction, button: Button):
        global bot_enabled
        if not bot_enabled:
            await interaction.response.send_message(
                embed=discord.Embed(description="🔴 Le bot est actuellement **hors ligne**.", color=ERR_COLOR),
                ephemeral=True,
            )
            return

        member_ok = await is_member_of_required_guild(interaction.user.id)
        if not member_ok:
            embed = discord.Embed(color=ERR_COLOR)
            embed.set_author(name=f"🚫 Accès refusé — {AI_NAME}")
            embed.description = (
                f"**Tu dois être membre de notre serveur pour utiliser ce bot.**\n\n"
                f"Rejoins le serveur en cliquant sur le lien ci-dessous :\n"
                f"🔗 **{INVITE_LINK}**"
            )
            embed.set_footer(text=f"Rejoint le serveur puis réessaie  •  {AI_NAME}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        sessions[interaction.user.id] = {}
        await interaction.response.send_modal(FormulaireModal1())


# ════════════════════════════════════════════════════════════════════════════
#  MENU D'ACCÈS — Message permanent avec 2 boutons
#  • Bouton 1 : "Vérifier mon accès"  → toujours cliquable
#  • Bouton 2 : "Créer du code Verse" → grisé si pas accès, actif si accès
#
#  Le message est RE-ENVOYÉ en éphémère à l'utilisateur avec les bons états
#  de boutons selon son accès. Le message public reste toujours le même
#  (avec le bouton Verse grisé par défaut pour les non-vérifiés).
# ════════════════════════════════════════════════════════════════════════════

class AccessMenuView(View):
    """
    Vue persistante — message public permanent.
    Bouton Verse toujours DISABLED ici (affiché grisé publiquement).
    Chaque utilisateur reçoit sa propre vue éphémère avec le bon état.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Vérifier mon accès",
        style=discord.ButtonStyle.success,
        emoji="🔓",
        custom_id="spectrax_access_check_v2"
    )
    async def check_access(self, interaction: discord.Interaction, button: Button):
        guild = bot.get_guild(MENU_GUILD_ID)
        if guild is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Serveur introuvable.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        member = guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except Exception:
                member = None

        if member is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Tu ne sembles pas être sur ce serveur.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        # ── Déjà vérifié : re-check statut permanent
        if interaction.user.id in verified_users:
            status_ok = has_required_status(member)
            if not status_ok:
                verified_users.discard(interaction.user.id)
                embed = discord.Embed(color=ERR_COLOR)
                embed.set_author(name="🚫 Accès révoqué")
                embed.description = (
                    "Ton accès a été **révoqué** car tu as **retiré ou changé ton statut**.\n\n"
                    f"Remet **`{REQUIRED_STATUS}`** dans ton statut Discord et reclique le bouton."
                )
                # Renvoyer la vue avec Verse désactivé
                await interaction.response.send_message(
                    embed=embed,
                    view=UserAccessView(verse_enabled=False),
                    ephemeral=True
                )
                return

            embed = discord.Embed(color=OK_COLOR)
            embed.set_author(name="✅ Accès confirmé")
            embed.description = (
                "Tu as déjà l'accès ! Toutes tes conditions sont remplies.\n\n"
                "Clique **Créer du code Verse** ci-dessous pour générer ton code !"
            )
            embed.set_footer(text=f"{AI_NAME}  •  Accès permanent actif")
            await interaction.response.send_message(
                embed=embed,
                view=UserAccessView(verse_enabled=True),
                ephemeral=True
            )
            return

        # ── Vérification des conditions
        conditions = await check_access_conditions(member)
        status_ok = conditions["status_ok"]
        invite_ok = conditions["invite_ok"]

        status_line = "✅ Statut trouvé" if status_ok else f"❌ Statut manquant — mets **`{REQUIRED_STATUS}`** dans ton statut Discord"
        invite_line = "✅ Invitation validée" if invite_ok else "❌ Invitation manquante — invite **5 personnes** sur ce serveur via ton lien perso"

        embed = discord.Embed(color=BOT_COLOR)
        embed.set_author(name=f"🔍 Vérification — {AI_NAME}")
        embed.description = (
            f"**Résultat des vérifications :**\n\n"
            f"{'🟢' if status_ok else '🔴'} **Statut Discord :** {status_line}\n"
            f"{'🟢' if invite_ok else '🔴'} **Invitation :** {invite_line}\n"
        )

        if conditions["all_ok"]:
            verified_users.add(interaction.user.id)
            embed.color = OK_COLOR
            embed.description += (
                "\n\n🎉 **Toutes les conditions sont remplies !**\n"
                "Tu as maintenant accès **pour toujours**.\n"
                "Clique le bouton **Créer du code Verse** ci-dessous !"
            )
            embed.set_footer(text=f"{AI_NAME}  •  Accès accordé à {datetime.datetime.now().strftime('%H:%M:%S')}")
            await interaction.response.send_message(
                embed=embed,
                view=UserAccessView(verse_enabled=True),
                ephemeral=True
            )
        else:
            embed.color = ERR_COLOR
            embed.description += (
                "\n\n> ⚠️ **Regarde au-dessus** pour voir ce qu'il te manque, puis reclique **Vérifier mon accès** une fois que c'est fait."
            )
            embed.set_footer(text=f"{AI_NAME}  •  Vérifié à {datetime.datetime.now().strftime('%H:%M:%S')}")
            await interaction.response.send_message(
                embed=embed,
                view=UserAccessView(verse_enabled=False),
                ephemeral=True
            )

    @discord.ui.button(
        label="Créer du code Verse",
        style=discord.ButtonStyle.blurple,
        emoji="⚡",
        custom_id="spectrax_verse_public_disabled_v2",
        disabled=True   # ← toujours grisé sur le message public
    )
    async def verse_public(self, interaction: discord.Interaction, button: Button):
        # Ce bouton est disabled donc ne sera jamais appelé sur le message public
        pass


class UserAccessView(View):
    """
    Vue envoyée à l'utilisateur après vérification.
    verse_enabled=True  → bouton Verse actif (bleu)
    verse_enabled=False → bouton Verse grisé
    """
    def __init__(self, verse_enabled: bool):
        super().__init__(timeout=None)   # ← None obligatoire pour add_view()
        self.verse_enabled = verse_enabled

        # Bouton Vérifier (toujours actif pour re-check)
        verify_btn = Button(
            label="Vérifier mon accès",
            style=discord.ButtonStyle.success,
            emoji="🔓",
            custom_id="spectrax_recheck_v2",
            row=0
        )
        verify_btn.callback = self.recheck_callback
        self.add_item(verify_btn)

        # Bouton Verse (actif ou grisé selon l'accès)
        verse_btn = Button(
            label="Créer du code Verse",
            style=discord.ButtonStyle.blurple if verse_enabled else discord.ButtonStyle.secondary,
            emoji="⚡",
            custom_id="spectrax_verse_user_v2",
            disabled=not verse_enabled,
            row=0
        )
        verse_btn.callback = self.verse_callback
        self.add_item(verse_btn)

    async def recheck_callback(self, interaction: discord.Interaction):
        """Re-vérifier les conditions depuis la vue éphémère."""
        guild = bot.get_guild(MENU_GUILD_ID)
        member = guild.get_member(interaction.user.id) if guild else None
        if member is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Impossible de te trouver sur ce serveur.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        conditions = await check_access_conditions(member)
        status_ok = conditions["status_ok"]
        invite_ok = conditions["invite_ok"]

        status_line = "✅ Statut trouvé" if status_ok else f"❌ Statut manquant — mets **`{REQUIRED_STATUS}`** dans ton statut Discord"
        invite_line = "✅ Invitation validée" if invite_ok else "❌ Invitation manquante — invite **5 personnes** sur ce serveur"

        embed = discord.Embed(color=BOT_COLOR)
        embed.set_author(name=f"🔍 Vérification — {AI_NAME}")
        embed.description = (
            f"**Résultat des vérifications :**\n\n"
            f"{'🟢' if status_ok else '🔴'} **Statut Discord :** {status_line}\n"
            f"{'🟢' if invite_ok else '🔴'} **Invitation :** {invite_line}\n"
        )

        if conditions["all_ok"]:
            verified_users.add(interaction.user.id)
            embed.color = OK_COLOR
            embed.description += (
                "\n\n🎉 **Toutes les conditions sont remplies !**\n"
                "Clique **Créer du code Verse** ci-dessous !"
            )
            embed.set_footer(text=f"{AI_NAME}  •  Accès accordé")
            await interaction.response.edit_message(
                embed=embed,
                view=UserAccessView(verse_enabled=True)
            )
        else:
            embed.color = ERR_COLOR
            embed.description += "\n\n> ⚠️ **Regarde au-dessus** pour voir ce qu'il te manque."
            embed.set_footer(text=f"{AI_NAME}  •  Pas encore validé")
            await interaction.response.edit_message(
                embed=embed,
                view=UserAccessView(verse_enabled=False)
            )

    async def verse_callback(self, interaction: discord.Interaction):
        """Lance le formulaire de génération de code Verse."""
        if not self.verse_enabled:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Tu n'as pas encore l'accès.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        # Vérifier que l'accès est toujours valide
        if interaction.user.id not in verified_users and not is_creator(interaction.user.id):
            embed = discord.Embed(color=ERR_COLOR)
            embed.description = "🚫 Ton accès a expiré. Reclique **Vérifier mon accès**."
            await interaction.response.edit_message(
                embed=embed,
                view=UserAccessView(verse_enabled=False)
            )
            return

        if not bot_enabled:
            await interaction.response.send_message(
                embed=discord.Embed(description="🔴 Le bot est actuellement **hors ligne**.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        sessions[interaction.user.id] = {}
        await interaction.response.send_modal(FormulaireModal1())


# ════════════════════════════════════════════════════════════════════════════
#  FLASK DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpectraX AI — Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#080c14;--surface:#0d1320;--surface2:#111827;--border:#1e2d45;--accent:#5865f2;--accent2:#00d4ff;--green:#57f287;--red:#ed4245;--text:#e2e8f0;--muted:#64748b;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Share Tech Mono',monospace;min-height:100vh;}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 20% 20%,rgba(88,101,242,0.06) 0%,transparent 60%),radial-gradient(ellipse at 80% 80%,rgba(0,212,255,0.04) 0%,transparent 60%);pointer-events:none;}
header{padding:24px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:rgba(13,19,32,0.8);backdrop-filter:blur(12px);position:sticky;top:0;z-index:100;}
.logo{display:flex;align-items:center;gap:14px;}
.logo-icon{width:44px;height:44px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;}
.logo-text{font-family:'Orbitron',monospace;font-weight:900;font-size:18px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.logo-sub{font-size:11px;color:var(--muted);margin-top:2px;}
.status-pill{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:999px;border:1px solid var(--border);background:var(--surface);font-size:13px;}
.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
main{padding:32px;max-width:1200px;margin:0 auto;}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:32px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:24px;position:relative;overflow:hidden;transition:border-color .2s,transform .2s;}
.card:hover{border-color:var(--accent);transform:translateY(-2px);}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),var(--accent2));opacity:0;transition:opacity .2s;}
.card:hover::before{opacity:1;}
.card-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;}
.card-value{font-family:'Orbitron',monospace;font-size:36px;font-weight:900;background:linear-gradient(135deg,var(--text),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.card-value.green{background:linear-gradient(135deg,var(--green),#00ff88);-webkit-background-clip:text;}
.card-value.red{background:linear-gradient(135deg,var(--red),#ff6b6b);-webkit-background-clip:text;}
.card-icon{position:absolute;top:20px;right:20px;font-size:28px;opacity:0.15;}
.section-title{font-family:'Orbitron',monospace;font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:2px;margin-bottom:16px;display:flex;align-items:center;gap:10px;}
.section-title::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent);}
.table-wrap{background:var(--surface);border:1px solid var(--border);border-radius:16px;overflow:hidden;}
table{width:100%;border-collapse:collapse;}
th{padding:14px 20px;text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--border);background:var(--surface2);}
td{padding:14px 20px;font-size:13px;border-bottom:1px solid rgba(30,45,69,0.5);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(88,101,242,0.04);}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;}
.badge-ok{background:rgba(87,242,135,0.1);color:var(--green);border:1px solid rgba(87,242,135,0.2);}
.badge-err{background:rgba(237,66,69,0.1);color:var(--red);border:1px solid rgba(237,66,69,0.2);}
.time-col{color:var(--muted);font-size:12px;}.user-col{color:var(--accent2);}
.empty-row td{text-align:center;color:var(--muted);padding:40px;}
.refresh-btn{padding:8px 20px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:8px;color:white;font-family:'Share Tech Mono',monospace;font-size:13px;cursor:pointer;transition:opacity .2s;}
.refresh-btn:hover{opacity:.85;}
</style></head><body>
<header>
  <div class="logo"><div class="logo-icon">🌌</div><div><div class="logo-text">SpectraX AI</div><div class="logo-sub">Dashboard — UEFN Verse Bot</div></div></div>
  <div style="display:flex;gap:12px;align-items:center;">
    <button class="refresh-btn" onclick="loadStats()">⟳ Actualiser</button>
    <div class="status-pill"><div class="dot" id="dot"></div><span id="status-text">Connexion...</span></div>
  </div>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="card-icon">⚡</div><div class="card-label">Codes générés</div><div class="card-value green" id="total-gen">—</div></div>
    <div class="card"><div class="card-icon">❌</div><div class="card-label">Erreurs</div><div class="card-value red" id="total-err">—</div></div>
    <div class="card"><div class="card-icon">🤖</div><div class="card-label">Bot Discord</div><div class="card-value" id="bot-name" style="font-size:16px;padding-top:8px;">—</div></div>
    <div class="card"><div class="card-icon">🕐</div><div class="card-label">Démarré le</div><div class="card-value" id="start-time" style="font-size:14px;padding-top:8px;">—</div></div>
  </div>
  <div class="section-title">Dernières requêtes</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Heure</th><th>Utilisateur</th><th>Projet</th><th>Statut</th></tr></thead>
    <tbody id="req-body"><tr class="empty-row"><td colspan="4">Aucune requête...</td></tr></tbody>
  </table></div>
</main>
<script>
async function loadStats(){
  try{
    const d=await(await fetch('/api/stats')).json();
    document.getElementById('total-gen').textContent=d.total_generations;
    document.getElementById('total-err').textContent=d.total_errors;
    document.getElementById('bot-name').textContent=d.bot_name||'Démarrage...';
    document.getElementById('start-time').textContent=d.start_time;
    const ok=d.bot_status==='online';
    document.getElementById('dot').style.background=ok?'var(--green)':'var(--red)';
    document.getElementById('status-text').textContent=ok?'● En ligne':'● Hors ligne';
    document.getElementById('req-body').innerHTML=d.last_requests?.length
      ?d.last_requests.map(r=>`<tr><td class="time-col">${r.time}</td><td class="user-col">@${r.user}</td><td>${r.feature}</td><td><span class="badge ${r.success?'badge-ok':'badge-err'}">${r.success?'✓ Succès':'✗ Erreur'}</span></td></tr>`).join('')
      :'<tr class="empty-row"><td colspan="4">Aucune requête...</td></tr>';
  }catch(e){document.getElementById('dot').style.background='var(--red)';}
}
loadStats();setInterval(loadStats,10000);
</script></body></html>"""

@app.route("/")
def dashboard(): return render_template_string(DASHBOARD_HTML)

@app.route("/api/stats")
def api_stats(): return jsonify(stats)

def run_flask():
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False)


# ════════════════════════════════════════════════════════════════════════════
#  VUE +VERIFON — Système de vérification par captcha (code aléatoire)
# ════════════════════════════════════════════════════════════════════════════

def generate_captcha_code(length: int = 6) -> str:
    """Génère un code aléatoire en majuscules (lettres + chiffres)."""
    chars = string.ascii_uppercase + string.digits
    # Retire les caractères ambigus (0/O, 1/I/L)
    chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "").replace("L", "")
    return "".join(random.choices(chars, k=length))


class CaptchaModal(discord.ui.Modal, title="✅ Vérification — Tape le code"):
    reponse = discord.ui.TextInput(
        label="Code de vérification",
        placeholder="Tape le code exactement comme indiqué...",
        required=True,
        min_length=4,
        max_length=8,
    )

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        expected = captcha_sessions.get(uid)

        if expected is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Ta session a expiré. Reclique le bouton **Vérification** pour recommencer.",
                    color=ERR_COLOR
                ),
                ephemeral=True
            )
            return

        if self.reponse.value.strip().upper() != expected:
            # Mauvaise réponse → nouveau captcha
            new_code = generate_captcha_code()
            captcha_sessions[uid] = new_code
            embed = discord.Embed(color=ERR_COLOR)
            embed.set_author(name="❌ Code incorrect — Nouvel essai")
            embed.description = (
                f"Le code que tu as tapé est **incorrect**.\n\n"
                f"🔐 **Nouveau code :** `{new_code}`\n\n"
                "Tape ce code **exactement** (majuscules) puis reclique le bouton."
            )
            embed.set_footer(text="SpectraX Vérification — Réessaie !")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"[CAPTCHA] {interaction.user} — mauvaise réponse sur '{interaction.guild}'")
            return

        # ✅ Bon code → donner le rôle
        captcha_sessions.pop(uid, None)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Impossible de trouver le serveur.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        role = guild.get_role(VERIFY_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Rôle introuvable (ID `{VERIFY_ROLE_ID}`). Contacte un admin.",
                    color=ERR_COLOR
                ),
                ephemeral=True
            )
            logger.error(f"[CAPTCHA] Rôle {VERIFY_ROLE_ID} introuvable sur '{guild.name}'")
            return

        member = guild.get_member(uid)
        if member is None:
            try:
                member = await guild.fetch_member(uid)
            except Exception:
                member = None

        if member is None:
            await interaction.response.send_message(
                embed=discord.Embed(description="❌ Impossible de te trouver sur ce serveur.", color=ERR_COLOR),
                ephemeral=True
            )
            return

        try:
            await member.add_roles(role, reason="SpectraX — Vérification captcha réussie")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Je n'ai pas la permission d'attribuer ce rôle. Contacte un admin.",
                    color=ERR_COLOR
                ),
                ephemeral=True
            )
            logger.error(f"[CAPTCHA] Permission manquante pour attribuer le rôle sur '{guild.name}'")
            return

        embed = discord.Embed(color=OK_COLOR)
        embed.set_author(name="✅ Vérification réussie !", icon_url=member.display_avatar.url)
        embed.description = (
            f"Bienvenue **{member.display_name}** ! 🎉\n\n"
            f"Tu as reçu le rôle **{role.mention}**.\n"
            "Tu as maintenant accès au serveur !"
        )
        embed.set_footer(text=f"SpectraX Vérification  •  {datetime.datetime.now().strftime('%H:%M:%S')}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"[CAPTCHA] {member} vérifié avec succès sur '{guild.name}' → rôle {role.name}")


class VerifView(View):
    """
    Vue persistante envoyée par +verifon.
    Bouton unique → génère un captcha et ouvre le modal.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cliquez ici pour vous vérifier",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="spectrax_verif_captcha_v1"
    )
    async def start_verif(self, interaction: discord.Interaction, button: Button):
        uid = interaction.user.id

        # Vérifier si l'user a déjà le rôle
        if interaction.guild:
            member = interaction.guild.get_member(uid)
            if member:
                role = interaction.guild.get_role(VERIFY_ROLE_ID)
                if role and role in member.roles:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            description="✅ Tu es déjà vérifié !",
                            color=OK_COLOR
                        ),
                        ephemeral=True
                    )
                    return

        # Générer un nouveau code captcha
        code = generate_captcha_code()
        captcha_sessions[uid] = code

        # Envoyer le code en éphémère AVANT d'ouvrir le modal
        embed = discord.Embed(color=BOT_COLOR)
        embed.set_author(name="🔐 Vérification — SpectraX")
        embed.description = (
            f"**Ton code de vérification :**\n\n"
            f"# `{code}`\n\n"
            "Tape ce code **exactement** (majuscules) dans le formulaire.\n"
            "> ⚠️ Code sensible à la casse — tape-le en **MAJUSCULES**"
        )
        embed.set_footer(text="SpectraX Vérification  •  Ce code expire si tu fermes la fenêtre")

        await interaction.response.send_message(embed=embed, view=CaptchaAnswerView(uid), ephemeral=True)


class CaptchaAnswerView(View):
    """Vue éphémère avec le bouton pour ouvrir le modal de saisie."""
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid

    @discord.ui.button(label="Entrer le code →", style=discord.ButtonStyle.blurple, emoji="⌨️")
    async def enter_code(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Pas ta vérification !", ephemeral=True)
            return
        await interaction.response.send_modal(CaptchaModal())

    async def on_timeout(self):
        captcha_sessions.pop(self.uid, None)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDES CRÉATEUR
# ════════════════════════════════════════════════════════════════════════════

async def handle_creator_command(message: discord.Message):
    global bot_enabled
    cmd = message.content.strip().lower()

    # +bon — allumer le bot
    if cmd == "+bon":
        bot_enabled = True
        embed = discord.Embed(color=OK_COLOR)
        embed.description = "🟢**BOT ONLINE**🟢\nLe bot est maintenant **activé**."
        await message.channel.send(embed=embed)
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="🟢 BOT ONLINE 🟢"),
        )
        # Renommer le salon vocal si l'auteur est dans un vocal
        if message.author.voice and message.author.voice.channel:
            try:
                await message.author.voice.channel.edit(name="🟢BOT ONLINE🟢")
            except Exception:
                pass
        logger.info(f"[BOT] Allumé par {message.author}")

    # +boff — éteindre le bot
    elif cmd == "+boff":
        bot_enabled = False
        embed = discord.Embed(color=ERR_COLOR)
        embed.description = "🔴**BOT OFFLINE**🔴\nLe bot est maintenant **désactivé**."
        await message.channel.send(embed=embed)
        await bot.change_presence(
            status=discord.Status.do_not_disturb,
            activity=discord.Activity(type=discord.ActivityType.watching, name="🔴 BOT OFFLINE 🔴"),
        )
        # Renommer le salon vocal si l'auteur est dans un vocal
        if message.author.voice and message.author.voice.channel:
            try:
                await message.author.voice.channel.edit(name="🔴BOT OFFLINE🔴")
            except Exception:
                pass
        logger.info(f"[BOT] Éteint par {message.author}")

    # +resetbot — redémarrer le bot
    elif cmd == "+resetbot":
        embed = discord.Embed(color=GOLD_COLOR)
        embed.description = "🔄 Redémarrage du bot dans 3 secondes..."
        await message.channel.send(embed=embed)
        await asyncio.sleep(3)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # +salon vocal — infos + renomme le salon selon le statut du bot
    elif cmd == "+salon vocal":
        if message.author.voice and message.author.voice.channel:
            channel = message.author.voice.channel
            members_in = [m for m in channel.members if not m.bot]

            # Renommer le salon selon le statut actuel du bot
            new_name = "🟢BOT ONLINE🟢" if bot_enabled else "🔴BOT OFFLINE🔴"
            try:
                await channel.edit(name=new_name)
            except Exception:
                pass

            embed = discord.Embed(color=BOT_COLOR, title="🎙️ Salon vocal")
            embed.add_field(name="📌 Salon",     value=f"**{new_name}**", inline=True)
            embed.add_field(name="👥 Membres",   value=f"{len(members_in)} connecté(s)", inline=True)
            embed.add_field(name="🆔 ID",        value=f"`{channel.id}`", inline=True)
            if members_in:
                embed.add_field(name="🎤 Connectés", value="\n".join(f"• {m.display_name}" for m in members_in[:10]), inline=False)
            embed.add_field(name="🤖 Statut bot", value="🟢BOT ONLINE🟢" if bot_enabled else "🔴BOT OFFLINE🔴", inline=False)
            embed.set_footer(text=f"{message.author.display_name} est dans ce salon")
            await message.channel.send(embed=embed)
            logger.info(f"[VOCAL] {message.author} — salon renommé '{new_name}'")
        else:
            embed = discord.Embed(color=ERR_COLOR)
            embed.description = "❌ Tu n'es pas dans un salon vocal !"
            await message.channel.send(embed=embed)

    # +createmenu — envoie le menu d'accès permanent (OWNER seulement, serveur MENU_GUILD_ID seulement)
    elif cmd == "+createmenu":
        # Vérification : seulement l'owner
        if message.author.id != OWNER_ID:
            await message.channel.send(
                embed=discord.Embed(description="❌ Seul le créateur peut faire cette commande.", color=ERR_COLOR)
            )
            return
        # Vérification : seulement sur le bon serveur
        if not message.guild or message.guild.id != MENU_GUILD_ID:
            await message.channel.send(
                embed=discord.Embed(description="❌ Cette commande ne fonctionne que sur le serveur autorisé.", color=ERR_COLOR)
            )
            return

        embed = discord.Embed(color=PURPLE)
        embed.set_author(name=f"🌌 {AI_NAME} — Accès Pro Dev UEFN")
        embed.title = "🔐 Accès — Créateur Verse UEFN"
        embed.description = (
            "**Pour accéder au générateur de code Verse, tu dois remplir les conditions suivantes :**\n\n"
            f"**1.** 🟣 Avoir **`{REQUIRED_STATUS}`** dans ton **statut Discord**\n"
            "**2.** 👥 Avoir **invité au moins 5 personnes** sur ce serveur\n"
            "**3.** 🏠 Être **membre de ce serveur** (condition permanente)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "**1.** Clique **🔓 Vérifier mon accès** pour checker tes conditions.\n"
            "**2.** Une fois validé, le bouton **⚡ Créer du code Verse** s'activera.\n"
            "⚠️ Si tu retires ton statut ou quittes le serveur, ton accès sera **révoqué**.\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        embed.set_footer(text=f"{AI_NAME}  •  Ce message est permanent")

        await message.channel.send(embed=embed, view=AccessMenuView())
        # Supprimer la commande pour garder le salon propre
        try:
            await message.delete()
        except Exception:
            pass

    # +logon — activer le système de logs sur ce serveur
    elif cmd == "+logon":
        if not message.guild:
            await message.channel.send(embed=discord.Embed(description="❌ Cette commande doit être utilisée sur un serveur.", color=ERR_COLOR))
            return
        guild = message.guild
        embed_load = discord.Embed(color=BOT_COLOR)
        embed_load.description = "⚙️ Création des salons de logs en cours..."
        msg = await message.channel.send(embed=embed_load)
        try:
            channels_map = await setup_log_channels(guild)
            embed_ok = discord.Embed(color=OK_COLOR, title="✅ Système de logs activé !")
            embed_ok.description = (
                "Les salons de logs suivants ont été créés dans la catégorie **📋 LOGS SPECTRAX** :\n\n"
                f"📝 **Logs messages** → <#{channels_map['messages']}>\n"
                f"🔨 **Logs sanctions** → <#{channels_map['sanctions']}>\n"
                f"🏗️ **Logs salons** → <#{channels_map['salons']}>\n"
                f"🎭 **Logs rôles** → <#{channels_map['roles']}>\n"
                f"📸 **Snapshot** → <#{channels_map['snapshot']}>\n\n"
                "**Protections actives :**\n"
                f"🛡️ Quarantaine auto si **+{CHANNEL_MOD_LIMIT} modifs de salon en {CHANNEL_MOD_WINDOW}s**\n"
                f"🛡️ Quarantaine auto si **+{BAN_LIMIT} bans en {BAN_WINDOW}s**\n"
                f"📸 Snapshot automatique toutes les **2 minutes**\n"
                f"🔄 Restauration automatique des salons supprimés\n"
                f"📩 Alertes DM au créateur en cas d'infraction"
            )
            embed_ok.set_footer(text=f"SpectraX Logs — activé le {now_str()}")
            await msg.edit(embed=embed_ok)
            logger.info(f"[LOGON] Logs activés sur '{guild.name}' par {message.author}")
        except Exception as e:
            await msg.edit(embed=discord.Embed(description=f"❌ Erreur : `{e}`", color=ERR_COLOR))
            logger.error(f"[LOGON] Erreur setup logs sur '{guild.name}': {e}")

    # +verifon — envoie un message de vérification dans le salon courant
    elif cmd == "+verifon":
        if not message.guild:
            await message.channel.send(
                embed=discord.Embed(description="❌ Cette commande doit être utilisée sur un serveur.", color=ERR_COLOR)
            )
            return

        embed = discord.Embed(color=PURPLE)
        embed.set_author(name=f"🔐 {AI_NAME} — Vérification")
        embed.title = "✅ Vérification du serveur"
        embed.description = (
            "**Bienvenue sur le serveur !**\n\n"
            "Pour accéder au serveur, tu dois te vérifier.\n\n"
            "**Comment ça marche :**\n"
            "**1.** Clique le bouton **✅ Cliquez ici pour vous vérifier**\n"
            "**2.** Un code unique s'affichera — **recopie-le exactement**\n"
            "**3.** Tu reçois automatiquement ton rôle de membre !\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "> 🤖 Ce système nous protège contre les bots et raids."
        )
        embed.set_footer(text=f"{AI_NAME}  •  Vérification automatique")

        await message.channel.send(embed=embed, view=VerifView())
        try:
            await message.delete()
        except Exception:
            pass
        logger.info(f"[VERIFON] Panel de vérification envoyé dans #{message.channel.name} par {message.author}")

    # +cmd — liste des commandes créateur
    elif cmd == "+cmd":
        embed = discord.Embed(color=GOLD_COLOR)
        embed.set_author(name=f"👑 Commandes Créateur — {AI_NAME}")
        embed.description = (
            "```\n"
            "+bon          → 🟢 Allumer le bot\n"
            "+boff         → 🔴 Éteindre le bot\n"
            "+resetbot     → 🔄 Redémarrer le bot\n"
            "+salon vocal  → 🎙️ Afficher le salon vocal\n"
            "+createmenu   → 📋 Créer le menu d'accès permanent\n"
            "+verifon      → ✅ Envoyer le panel de vérification\n"
            "+logon        → 📋 Activer les logs sur ce serveur\n"
            "+cmd          → 📋 Cette liste\n"
            "```"
        )
        embed.set_footer(text=f"Commandes réservées aux créateurs  •  {AI_NAME}")
        await message.channel.send(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS DISCORD
# ════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    # Ré-enregistrer les vues persistantes au redémarrage
    bot.add_view(StartView())
    bot.add_view(AccessMenuView())
    bot.add_view(UserAccessView(verse_enabled=True))
    bot.add_view(UserAccessView(verse_enabled=False))
    bot.add_view(VerifView())
    stats["bot_status"] = "online"
    stats["bot_name"]   = str(bot.user)
    logger.info(f"Bot connecté    : {bot.user}")
    logger.info(f"Serveur requis  : {REQUIRED_GUILD_ID}")
    logger.info(f"Serveur menu    : {MENU_GUILD_ID}")
    logger.info(f"IA              : {AI_NAME}")
    logger.info(f"Dashboard       : http://localhost:{DASHBOARD_PORT}")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="🟢 BOT ONLINE 🟢"),
    )
    # Lancer la boucle de snapshot
    bot.loop.create_task(auto_snapshot_loop())


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS LOGS — Messages
# ════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.guild.id not in log_channels_ids:
        return
    if message.author.bot:
        return
    embed = discord.Embed(color=0xED4245, title="🗑️ Message supprimé")
    embed.add_field(name="👤 Auteur",  value=f"{message.author.mention} (`{message.author}`)", inline=True)
    embed.add_field(name="📌 Salon",   value=message.channel.mention, inline=True)
    embed.add_field(name="💬 Contenu", value=message.content[:1000] if message.content else "*[pas de texte]*", inline=False)
    embed.set_footer(text=now_str())
    await send_log(message.guild, "messages", embed)
    logger.debug(f"[MSG DELETE] {message.author} dans #{message.channel.name}")


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.guild.id not in log_channels_ids:
        return
    if before.author.bot or before.content == after.content:
        return
    embed = discord.Embed(color=0xF1C40F, title="✏️ Message modifié")
    embed.add_field(name="👤 Auteur",   value=f"{before.author.mention} (`{before.author}`)", inline=True)
    embed.add_field(name="📌 Salon",    value=before.channel.mention, inline=True)
    embed.add_field(name="📝 Avant",    value=before.content[:500] or "*vide*", inline=False)
    embed.add_field(name="✅ Après",    value=after.content[:500] or "*vide*", inline=False)
    embed.add_field(name="🔗 Lien",     value=f"[Aller au message]({after.jump_url})", inline=False)
    embed.set_footer(text=now_str())
    await send_log(before.guild, "messages", embed)


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS LOGS — Sanctions / Bans
# ════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if guild.id not in log_channels_ids:
        return

    # ── Anti-raid : 5 bans en moins de 60 secondes
    now = datetime.datetime.now().timestamp()
    if guild.id not in ban_tracker:
        ban_tracker[guild.id] = []
    ban_tracker[guild.id].append(now)
    # Nettoyer les timestamps hors fenêtre
    ban_tracker[guild.id] = [t for t in ban_tracker[guild.id] if now - t <= BAN_WINDOW]

    if len(ban_tracker[guild.id]) >= BAN_LIMIT:
        ban_tracker[guild.id] = []  # reset pour éviter le spam
        # Trouver le responsable via l'audit log
        executor = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                executor = entry.user
                break
        except Exception:
            pass
        if executor and not is_creator(executor.id):
            member_exec = guild.get_member(executor.id)
            await quarantine_member(
                guild, member_exec,
                reason=f"🚨 Trop de bans rapides ({BAN_LIMIT} en {BAN_WINDOW}s)",
                log_key="sanctions"
            )

    # Log normal du ban
    embed = discord.Embed(color=0xED4245, title="🔨 Membre banni")
    embed.add_field(name="👤 Banni",  value=f"`{user}` ({user.id})", inline=True)
    embed.set_footer(text=now_str())
    await send_log(guild, "sanctions", embed)
    logger.warning(f"[BAN] {user} banni sur '{guild.name}'")


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    if guild.id not in log_channels_ids:
        return
    embed = discord.Embed(color=0x57F287, title="✅ Membre débanni")
    embed.add_field(name="👤 Débanni", value=f"`{user}` ({user.id})", inline=True)
    embed.set_footer(text=now_str())
    await send_log(guild, "sanctions", embed)


@bot.event
async def on_member_remove(member: discord.Member):
    # Révocation accès bot
    if member.guild.id == MENU_GUILD_ID:
        verified_users.discard(member.id)
    # Log kick (distinguer via audit log)
    if member.guild.id not in log_channels_ids:
        return
    try:
        async for entry in member.guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                embed = discord.Embed(color=0xE67E22, title="👢 Membre expulsé (kick)")
                embed.add_field(name="👤 Membre",  value=f"`{member}` ({member.id})", inline=True)
                embed.add_field(name="🔨 Par",     value=str(entry.user), inline=True)
                embed.add_field(name="📋 Raison",  value=entry.reason or "Aucune", inline=False)
                embed.set_footer(text=now_str())
                await send_log(member.guild, "sanctions", embed)
                logger.warning(f"[KICK] {member} expulsé sur '{member.guild.name}' par {entry.user}")
                return
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS LOGS — Salons (suppression / modification)
# ════════════════════════════════════════════════════════════════════════════

async def _track_channel_mod(guild: discord.Guild, executor: discord.Member | None, action_name: str):
    """Suivi anti-raid des modifications de salons. Quarantaine si > 3 en 30s."""
    if executor is None or is_creator(executor.id) or executor.bot:
        return
    now = datetime.datetime.now().timestamp()
    if guild.id not in channel_mod_tracker:
        channel_mod_tracker[guild.id] = {}
    uid = executor.id
    if uid not in channel_mod_tracker[guild.id]:
        channel_mod_tracker[guild.id][uid] = []
    channel_mod_tracker[guild.id][uid].append(now)
    # Nettoyer
    channel_mod_tracker[guild.id][uid] = [
        t for t in channel_mod_tracker[guild.id][uid] if now - t <= CHANNEL_MOD_WINDOW
    ]
    count = len(channel_mod_tracker[guild.id][uid])
    logger.debug(f"[ANTIRAID] {executor} — {count} modif(s) salon en {CHANNEL_MOD_WINDOW}s")
    if count >= CHANNEL_MOD_LIMIT:
        channel_mod_tracker[guild.id][uid] = []  # reset
        member = guild.get_member(executor.id)
        await quarantine_member(
            guild, member,
            reason=f"🚨 Trop de modifications de salons ({CHANNEL_MOD_LIMIT} en {CHANNEL_MOD_WINDOW}s) — {action_name}",
            log_key="salons"
        )


@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    if guild.id not in log_channels_ids:
        return

    executor = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_delete):
            if entry.target.id == channel.id:
                executor = entry.user
                break
    except Exception:
        pass

    await _track_channel_mod(guild, executor, f"suppression #{channel.name}")

    # Tentative de restauration automatique
    restored = await restore_channel(guild, channel.id, restored_by=str(executor) if executor else "auto")

    embed = discord.Embed(color=0xED4245, title="🗑️ Salon supprimé")
    embed.add_field(name="📌 Salon",       value=f"`#{channel.name}`", inline=True)
    embed.add_field(name="📂 Catégorie",   value=channel.category.name if channel.category else "Aucune", inline=True)
    embed.add_field(name="👤 Responsable", value=str(executor) if executor else "Inconnu", inline=True)
    embed.add_field(name="🔄 Restauré",    value="✅ Oui" if restored else "❌ Non", inline=True)
    embed.add_field(name="🕐 Date",        value=now_str(), inline=True)
    if restored:
        embed.add_field(name="ℹ️ Info", value="Le salon a été automatiquement recréé.", inline=False)
    embed.set_footer(text=f"SpectraX Logs — {guild.name}")
    await send_log(guild, "salons", embed)
    logger.warning(f"[CHANNEL DELETE] #{channel.name} sur '{guild.name}' — restauré: {restored}")

    # DM créateur si restauration effectuée
    if restored:
        owner = bot.get_user(OWNER_ID)
        if owner:
            try:
                await owner.send(embed=discord.Embed(
                    color=0x57F287,
                    title="🔄 Restauration automatique",
                    description=(
                        f"**Serveur :** `{guild.name}`\n"
                        f"**Salon supprimé :** `#{channel.name}`\n"
                        f"**Responsable :** {str(executor) if executor else 'Inconnu'}\n"
                        f"**Restauré le :** {now_str()}\n"
                        f"**Par :** SpectraX Auto-Restore"
                    )
                ))
            except Exception:
                pass


@bot.event
async def on_guild_channel_update(before, after):
    guild = before.guild
    if guild.id not in log_channels_ids:
        return
    if before.name == after.name and before.category == after.category:
        return  # rien d'intéressant

    executor = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_update):
            if entry.target.id == before.id:
                executor = entry.user
                break
    except Exception:
        pass

    await _track_channel_mod(guild, executor, f"modification #{before.name}")

    embed = discord.Embed(color=0xF1C40F, title="✏️ Salon modifié")
    if before.name != after.name:
        embed.add_field(name="📌 Nom avant", value=f"`{before.name}`", inline=True)
        embed.add_field(name="📌 Nom après", value=f"`{after.name}`", inline=True)
    if before.category != after.category:
        embed.add_field(name="📂 Catég. avant", value=before.category.name if before.category else "Aucune", inline=True)
        embed.add_field(name="📂 Catég. après", value=after.category.name if after.category else "Aucune", inline=True)
    embed.add_field(name="👤 Responsable", value=str(executor) if executor else "Inconnu", inline=False)
    embed.add_field(name="🕐 Date",        value=now_str(), inline=True)
    embed.set_footer(text=f"SpectraX Logs — {guild.name}")
    await send_log(guild, "salons", embed)


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS LOGS — Rôles (suppression / modification)
# ════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild = role.guild
    if guild.id not in log_channels_ids:
        return
    executor = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_delete):
            if entry.target.id == role.id:
                executor = entry.user
                break
    except Exception:
        pass
    embed = discord.Embed(color=0xED4245, title="🎭 Rôle supprimé")
    embed.add_field(name="🎭 Rôle",        value=f"`{role.name}`", inline=True)
    embed.add_field(name="👤 Responsable", value=str(executor) if executor else "Inconnu", inline=True)
    embed.add_field(name="🕐 Date",        value=now_str(), inline=True)
    embed.set_footer(text=f"SpectraX Logs — {guild.name}")
    await send_log(guild, "roles", embed)
    logger.warning(f"[ROLE DELETE] @{role.name} sur '{guild.name}'")


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    guild = before.guild
    if guild.id not in log_channels_ids:
        return
    if before.name == after.name and before.permissions == after.permissions and before.color == after.color:
        return
    executor = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_update):
            if entry.target.id == before.id:
                executor = entry.user
                break
    except Exception:
        pass
    embed = discord.Embed(color=0xF1C40F, title="✏️ Rôle modifié")
    if before.name != after.name:
        embed.add_field(name="📛 Nom avant", value=f"`{before.name}`", inline=True)
        embed.add_field(name="📛 Nom après", value=f"`{after.name}`", inline=True)
    if before.color != after.color:
        embed.add_field(name="🎨 Couleur avant", value=str(before.color), inline=True)
        embed.add_field(name="🎨 Couleur après", value=str(after.color), inline=True)
    if before.permissions != after.permissions:
        embed.add_field(name="⚙️ Permissions", value="Modifiées", inline=False)
    embed.add_field(name="👤 Responsable", value=str(executor) if executor else "Inconnu", inline=False)
    embed.add_field(name="🕐 Date",        value=now_str(), inline=True)
    embed.set_footer(text=f"SpectraX Logs — {guild.name}")
    await send_log(guild, "roles", embed)


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """
    Quand quelqu'un change son statut/activité, on vérifie s'il a perdu les conditions.
    """
    if not hasattr(after, 'guild') or after.guild is None:
        return
    if after.guild.id != MENU_GUILD_ID:
        return
    if after.id not in verified_users:
        return
    # Révoquer si le statut requis a disparu
    if not has_required_status(after):
        verified_users.discard(after.id)
        try:
            embed = discord.Embed(color=ERR_COLOR)
            embed.set_author(name=f"⚠️ Accès révoqué — {AI_NAME}")
            embed.description = (
                f"Ton accès a été **révoqué automatiquement** car tu as retiré ou changé ton statut Discord.\n\n"
                f"Remet **`{REQUIRED_STATUS}`** dans ton statut et reclique le bouton de vérification pour récupérer ton accès."
            )
            await after.send(embed=embed)
        except Exception:
            pass


async def handle_invites_command(message: discord.Message):
    """Affiche les invites de l'auteur ou d'un membre mentionné."""
    guild = message.guild
    if not guild:
        return

    # Déterminer la cible : mention ou l'auteur lui-même
    # On filtre les mentions de bots et on prend le premier vrai membre
    target = message.author
    for mention in message.mentions:
        if not mention.bot:
            target = mention
            break

    try:
        invites = await guild.invites()
    except discord.Forbidden:
        await message.channel.send(
            embed=discord.Embed(
                description=(
                    "❌ Je n'ai pas la permission **Gérer le serveur** pour lire les invitations.\n"
                    "Donne-moi cette permission et réessaie !"
                ),
                color=ERR_COLOR
            ),
            delete_after=10
        )
        return
    except Exception as e:
        logger.error(f"[INVITES] Erreur récupération invites sur '{guild.name}': {e}")
        await message.channel.send(
            embed=discord.Embed(description="❌ Impossible de récupérer les invitations.", color=ERR_COLOR),
            delete_after=8
        )
        return

    # Filtrer les invites de la cible
    user_invites = [inv for inv in invites if inv.inviter and inv.inviter.id == target.id]

    total_uses  = sum(inv.uses or 0 for inv in user_invites)
    total_links = len(user_invites)

    # Dernière invite créée
    last_invite = None
    if user_invites:
        last_invite = max(user_invites, key=lambda i: i.created_at if i.created_at else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

    # Calcul "il y a combien de temps"
    def time_ago(dt: datetime.datetime) -> str:
        if dt is None:
            return "inconnu"
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return f"{diff} seconde(s)"
        elif diff < 3600:
            return f"{diff // 60} minute(s)"
        elif diff < 86400:
            return f"{diff // 3600} heure(s)"
        else:
            return f"{diff // 86400} jour(s)"

    # Statut des conditions d'accès (5 invites requises)
    conditions_ok = total_uses >= 5
    progress_bar  = "🟩" * min(total_uses, 5) + "⬜" * max(0, 5 - total_uses)

    embed = discord.Embed(color=PURPLE if not conditions_ok else OK_COLOR)
    embed.set_author(
        name=f"📨 Invitations de {target.display_name}",
        icon_url=target.display_avatar.url
    )
    embed.add_field(
        name="🔗 Liens d'invitation",
        value=f"**{total_links}** lien(s) actif(s)",
        inline=True
    )
    embed.add_field(
        name="👥 Personnes rejointes",
        value=f"**{total_uses}** membre(s)",
        inline=True
    )
    embed.add_field(
        name="🎯 Progression (objectif : 5)",
        value=f"{progress_bar}  **{min(total_uses, 5)}/5**",
        inline=False
    )

    if last_invite:
        embed.add_field(
            name="🕐 Dernière invitation créée",
            value=f"Il y a **{time_ago(last_invite.created_at)}**  •  `{last_invite.code}`",
            inline=False
        )

    if total_links > 0:
        details = "\n".join(
            f"• `{inv.code}` — **{inv.uses or 0}** utilisé(s)"
            for inv in sorted(user_invites, key=lambda i: i.uses or 0, reverse=True)[:5]
        )
        embed.add_field(name="📋 Détail des liens (top 5)", value=details, inline=False)

    if conditions_ok:
        embed.set_footer(text="✅ Condition d'invitation remplie (5/5)")
    else:
        remaining = 5 - total_uses
        embed.set_footer(text=f"⏳ Encore {remaining} invitation(s) nécessaire(s) pour l'accès")

    await message.channel.send(embed=embed, delete_after=30)


@bot.event
async def on_message(message: discord.Message):
    global bot_enabled
    if message.author.bot:
        return

    # ── Commandes créateur (partout, priorité absolue)
    if is_creator(message.author.id) and message.content.strip().lower().startswith("+"):
        await handle_creator_command(message)
        return

    # ── Salon +invites : seule la commande est autorisée, tout le reste est supprimé
    if message.guild and message.channel.id == INVITES_CHANNEL_ID:
        content = message.content.strip().lower()
        if content.startswith("+invites"):
            # Traiter d'abord, supprimer après (pour garder les mentions accessibles)
            await handle_invites_command(message)
            try:
                await message.delete()
            except Exception:
                pass
        else:
            try:
                await message.delete()
            except Exception:
                pass
        return

    # Bot désactivé
    if not bot_enabled:
        return

    if not message.guild:
        return


# ════════════════════════════════════════════════════════════════════════════
#  LANCEMENT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"🌐  Dashboard lancé sur http://localhost:{DASHBOARD_PORT}")
    bot.run(DISCORD_TOKEN)