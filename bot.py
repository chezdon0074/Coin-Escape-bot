import discord
from discord.ext import commands, tasks
import os
import random
import aiohttp
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import tweepy
import re
import json

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
BEARER_TOKEN = os.getenv('BEARER_TOKEN')   # Read from .env – no fallback
ETHERSCAN_KEY = os.getenv('ETHERSCAN_API_KEY', '')   # Optional but recommended for !track ETH
BSCSCAN_KEY = os.getenv('BSCSCAN_API_KEY', '')       # Optional but recommended for !track BSC

# Bot configuration
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

APP_VERSION = "2.1.0"
SUPPORTED_EXCHANGES = ["Binance", "Bybit", "Coinbase", "Kraken", "KuCoin", "OKX", "Hyperliquid"]

# ============================================
# PERMISSION CHECK – VIP / ADMIN ROLES
# ============================================

ALLOWED_ROLES = {"vip", "admin"}  # Case-insensitive

def has_permission(ctx):
    """Check if user has a VIP/Admin role or is a server administrator."""
    if ctx.author.guild_permissions.administrator:
        return True
    user_roles = {role.name.lower() for role in ctx.author.roles}
    return bool(user_roles.intersection(ALLOWED_ROLES))

# ============================================
# TWITTER FUD / LARGE WITHDRAWAL ALERTS
# ============================================

# Only initialize if token is present and not empty
if BEARER_TOKEN:
    TWITTER_CLIENT = tweepy.Client(bearer_token=BEARER_TOKEN)
else:
    TWITTER_CLIENT = None
    print("⚠️ BEARER_TOKEN not set in .env – FUD alerts disabled.")

PROCESSED_FILE = "processed_tweets.json"

# Very low thresholds – catch almost anything
WITHDRAWAL_THRESHOLD = {
    "BTC": 0.1,
    "ETH": 1,
    "USDT": 1000,
    "USDC": 1000,
    "DAI": 1000,
    "XRP": 100,
    "ADA": 100,
    "SOL": 10,
    "DOT": 10,
    "AVAX": 10
}

# Expanded FUD keywords
FUD_TRIGGER_WORDS = [
    "bank run", "insolvent", "freeze withdrawals", "halt withdrawals",
    "collapse", "hack", "exploit", "panic", "suspends withdrawals",
    "liquidity crisis", "scam", "rug", "exit scam", "bankrupt",
    "withdrawal issue", "can't withdraw", "withdrawal delay",
    "withdrawal problem", "stuck withdrawal", "withdrawal halted",
    "funds frozen", "panic sell", "crash"
]

fud_last_run = None
fud_last_count = 0

def load_processed_ids():
    try:
        with open(PROCESSED_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_processed_ids(ids):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f)

# Exchanges we treat as "exchange-related" for !fud
EXCHANGE_NAMES = [
    "binance", "coinbase", "kraken", "bybit", "ftx", "okx", "huobi",
    "kucoin", "gate.io", "gate io", "crypto.com", "hyperliquid", "bitget",
    "mexc", "gemini", "bitfinex", "bitstamp", "upbit", "bithumb"
]

# Strong problem words that signal genuine exchange trouble
EXCHANGE_PROBLEM_WORDS = [
    "bank run", "insolvent", "freeze withdrawals", "halt withdrawals",
    "suspends withdrawals", "suspend withdrawals", "paused withdrawals",
    "pause withdrawals", "liquidity crisis", "bankrupt", "collapse",
    "hack", "exploit", "withdrawal issue", "can't withdraw",
    "cannot withdraw", "withdrawal delay", "freeze", "halt"
]

def analyze_tweet(text):
    """
    Returns: (amount, unit, reason, category)
      category is "exchange" (routed to !fud) or "news" (routed to !news).
    """
    text_lower = text.lower()
    mentions_exchange = any(name in text_lower for name in EXCHANGE_NAMES)

    # 1. Numeric large withdrawal
    pattern = r'(\d{1,3}(?:,\d{3})*)\s*(BTC|ETH|USDT|USDC|DAI|XRP|ADA|SOL|DOT|AVAX)'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        raw = match.group(1).replace(",", "")
        amount = float(raw)
        unit = match.group(2).upper()
        if amount >= WITHDRAWAL_THRESHOLD.get(unit, 0):
            category = "exchange" if mentions_exchange else "news"
            return amount, unit, "💰 Large Withdrawal", category

    # 2. Exchange-specific FUD: named exchange AND a strong problem word
    if mentions_exchange:
        for word in EXCHANGE_PROBLEM_WORDS:
            if word in text_lower:
                return None, None, "🔥 Exchange FUD Alert", "exchange"

    # 3. Everything else that came back from the search query is general crypto news
    return None, None, "📰 Crypto News", "news"

def fetch_twitter_fud_tweets():
    if not TWITTER_CLIENT:
        return []
    
    # X API v2 rules: implicit AND (space), no '*' wildcards.
    query = (
        "(binance OR coinbase OR kraken OR bybit OR ftx OR okx OR huobi OR kucoin OR gate.io OR crypto.com OR exchange) "
        "(withdraw OR withdrawal OR withdrawals OR outflow OR outflows OR deposit OR transfer OR fud OR panic OR \"bank run\" OR insolvent OR freeze OR halt OR collapse OR hack OR scam OR rug) "
        "-is:retweet -is:reply lang:en"
    )
    end_time = datetime.utcnow() - timedelta(seconds=30)
    start_time = end_time - timedelta(hours=24)
    try:
        tweets = TWITTER_CLIENT.search_recent_tweets(
            query=query,
            tweet_fields=["created_at", "author_id"],
            max_results=100,
            start_time=start_time.isoformat(timespec="seconds") + "Z",
            end_time=end_time.isoformat(timespec="seconds") + "Z"
        )
        count = len(tweets.data) if tweets.data else 0
        print(f"🔍 Twitter fetch: {count} tweets found in the last 24h.")
        return tweets.data if tweets.data else []
    except Exception as e:
        print(f"❌ Twitter API error: {e}")
        return []

async def get_twitter_alerts(category=None):
    """Async wrapper – fetches new tweets and filters them.

    category: "exchange" -> only exchange FUD (for !fud)
              "news"     -> only general crypto news (for !news)
              None       -> everything
    """
    processed = load_processed_ids()
    new_alerts = []
    tweets = await asyncio.to_thread(fetch_twitter_fud_tweets)

    for tweet in tweets:
        if tweet.id in processed:
            continue

        amount, unit, reason, cat = analyze_tweet(tweet.text)
        if reason is None:
            continue

        if category is not None and cat != category:
            continue

        if amount:
            detail = f"{amount:,.0f} {unit} - {reason}"
        else:
            detail = reason

        new_alerts.append({
            "id": tweet.id,
            "text": tweet.text[:200],
            "url": f"https://twitter.com/i/web/status/{tweet.id}",
            "detail": detail,
            "category": cat,
            "created_at": tweet.created_at
        })
        processed.add(tweet.id)

    save_processed_ids(processed)
    return new_alerts

# ============================================
# BACKGROUND TASKS
# ============================================

@tasks.loop(minutes=5)
async def check_exchange_status_auto():
    channel_id = os.getenv('ALERT_CHANNEL_ID')
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ping", timeout=5) as resp:
                if resp.status != 200:
                    await channel.send(f"🔴 **ALERT:** Binance is having issues! Status: {resp.status}")
    except asyncio.TimeoutError:
        await channel.send("🔴 **ALERT:** Binance is not responding (timeout)!")
    except Exception as e:
        await channel.send(f"🔴 **ALERT:** Binance error: {str(e)[:50]}")

@tasks.loop(hours=1)
async def send_daily_report():
    channel_id = os.getenv('ALERT_CHANNEL_ID')
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as resp:
                data = await resp.json()
                btc_price = data.get('bitcoin', {}).get('usd', 'N/A')
                await channel.send(f"📊 **Daily Report**\nBitcoin: ${btc_price}\nAll systems operational")
    except:
        await channel.send("⚠️ Could not fetch price data")

@tasks.loop(hours=24)
async def send_twitter_fud_report():
    global fud_last_run, fud_last_count
    if not TWITTER_CLIENT:
        return
    channel_id = os.getenv('ALERT_CHANNEL_ID')
    if not channel_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    alerts = await get_twitter_alerts(category="exchange")
    fud_last_run = datetime.utcnow()
    fud_last_count = len(alerts)
    if not alerts:
        return
    embed = discord.Embed(
        title="🚨 Daily Exchange FUD & Large Withdrawal Alerts",
        description="Tweets mentioning large outflows or FUD in the last 24 hours:",
        color=0xff5500,
        timestamp=datetime.utcnow()
    )
    for alert in alerts[:10]:
        embed.add_field(
            name=f"{alert['detail']}",
            value=f"{alert['text']}... [Link]({alert['url']})",
            inline=False
        )
    embed.set_footer(text="Alerts auto-generated every 24h")
    await channel.send(embed=embed)

# ============================================
# EVENTS
# ============================================

@bot.event
async def on_ready():
    print(f'✅ Coin Escape Bot is online!')
    print(f'📊 Logged in as: {bot.user}')
    print(f'🌐 Connected to {len(bot.guilds)} servers')
    check_exchange_status_auto.start()
    send_daily_report.start()
    if TWITTER_CLIENT:
        send_twitter_fud_report.start()
        print("✅ Twitter FUD alert system started.")
    else:
        print("⚠️ Twitter client not configured – FUD alerts disabled.")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="crypto markets | !help"
    ))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Unknown command. Type `!help` for available commands.")
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"Error: {error}")

# ============================================
# ORIGINAL COMMANDS (preserved in full)
# ============================================

@bot.command()
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.command()
async def about(ctx):
    """About Coin Escape"""
    embed = discord.Embed(
        title="🪙 Coin Escape",
        description="Emergency panic withdrawal app for crypto exchanges. "
                    "Connect your exchange API keys and drain funds to self-custody "
                    "in one action when an exchange looks compromised.",
        color=0x00ff88
    )
    embed.add_field(name="Version", value=APP_VERSION, inline=True)
    embed.add_field(name="Security", value="AES-256-GCM encrypted on-device", inline=True)
    embed.add_field(name="GitHub", value="[View Source](https://github.com/chezdon0074/Coin-Escape-bot)", inline=False)
    embed.set_footer(text="🚀 Built for crypto security")
    await ctx.send(embed=embed)

@bot.command()
async def security(ctx):
    """Security model explanation"""
    embed = discord.Embed(
        title="🔐 Security Model",
        description="Coin Escape takes security seriously:",
        color=0x2ecc71
    )
    embed.add_field(
        name="🔒 On-Device Encryption",
        value="Credentials are encrypted using AES-256-GCM and stored in `expo-secure-store`.",
        inline=False
    )
    embed.add_field(
        name="🧠 Session Key",
        value="The session key lives only in memory—never persisted to disk.",
        inline=False
    )
    embed.add_field(
        name="🧪 Dry Run Mode",
        value="Test withdrawals without moving real funds before enabling Real Withdrawal.",
        inline=False
    )
    embed.set_footer(text="Your keys, your control")
    await ctx.send(embed=embed)

# ============================================
# HELP COMMAND
# ============================================

@bot.command()
async def help(ctx):
    """List all available commands"""
    embed = discord.Embed(
        title="📋 Coin Escape Commands",
        description="Here are all available commands:",
        color=0x00ff88
    )
    embed.add_field(
        name="📊 Basic",
        value="`!ping` - Check latency\n"
              "`!about` - About Coin Escape\n"
              "`!version` - Show version\n"
              "`!status` - Bot status\n"
              "`!help` - Show this menu",
        inline=False
    )
    embed.add_field(
        name="🔐 Security & Info",
        value="`!security` - Security model\n"
              "`!exchanges` - Supported exchanges\n"
              "`!faq` - Frequently asked questions\n"
              "`!guide` - Getting started guide",
        inline=False
    )
    embed.add_field(
        name="📊 Exchange & Prices",
        value="`!exchange_status` - Check if exchanges are online\n"
              "`!price <coin>` - Get crypto price\n"
              "`!btc` - Bitcoin price\n"
              "`!eth` - Ethereum price\n"
              "`!sol` - Solana price",
        inline=False
    )
    embed.add_field(
        name="🔍 Withdrawal Tools",
        value="`!withdraw-status <coin>` - Check deposit/withdraw status\n"
              "`!track <network> <txid>` - Track ANY transaction (SOL, ETH, BTC, BSC)\n"
              "`!support` - Binance support links\n"
              "`!coins` - Check top 10 coins deposit/withdraw status",
        inline=False
    )
    embed.add_field(
        name="🚨 Alerts & News (VIP/Admin only)",
        value="`!fud` - Exchange FUD & large withdrawal alerts (exchange-specific)\n"
              "`!news` - Broader crypto news & market FUD\n"
              "`!fud_status` - Status of the FUD alert system\n"
              "`!test_twitter` - Check the Twitter/X API connection\n"
              "`!fud_debug` - Debug raw tweets from the FUD query",
        inline=False
    )
    embed.set_footer(text="🔄 Automation features active")
    await ctx.send(embed=embed)

# ============================================
# TEST COMMANDS WITH COPY BUTTON
# ============================================

@bot.command()
async def testcmds(ctx):
    """Get a copyable list of test commands"""
    commands_text = (
        "!help\n"
        "!exchange_status\n"
        "!exchange_status binance\n"
        "!withdraw-status BTC\n"
        "!btc\n"
        "!ping"
    )
    
    class CopyButton(discord.ui.View):
        @discord.ui.button(label="📋 Copy All Commands", style=discord.ButtonStyle.primary)
        async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(f"```\n{commands_text}\n```", ephemeral=True)
    
    embed = discord.Embed(
        title="📋 Test Commands",
        description="Click the button below to copy all test commands to your clipboard.",
        color=0x00ff88
    )
    await ctx.send(embed=embed, view=CopyButton())

# ============================================
# GUIDE, FAQ, STATUS, VERSION, COINFLIP, SERVER
# ============================================

@bot.command()
async def guide(ctx):
    """Getting started guide"""
    embed = discord.Embed(
        title="📖 Getting Started",
        description="Follow the complete setup guide on GitHub:",
        color=0xe67e22
    )
    embed.add_field(
        name="🔗 Guide Link",
        value="https://github.com/chezdon0074/Coin-Escape-bot#readme",
        inline=False
    )
    embed.add_field(
        name="📱 Mobile App",
        value="Available for iOS and Android via Expo",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command()
async def faq(ctx):
    """Frequently asked questions"""
    embed = discord.Embed(
        title="❓ Frequently Asked Questions",
        color=0x9b59b6
    )
    embed.add_field(
        name="What is Coin Escape?",
        value="A panic withdrawal app that helps you quickly move funds from exchanges to self-custody.",
        inline=False
    )
    embed.add_field(
        name="Is it safe?",
        value="✅ Yes—keys are encrypted on-device. No server-side storage of credentials.",
        inline=False
    )
    embed.add_field(
        name="Which exchanges are supported?",
        value=f"{', '.join(SUPPORTED_EXCHANGES)}",
        inline=False
    )
    embed.add_field(
        name="Can I test it first?",
        value="✅ Yes! Use Dry Run mode to simulate withdrawals without moving real funds.",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    """Check bot and app status"""
    embed = discord.Embed(
        title="🟢 Status",
        description="All systems operational",
        color=0x2ecc71
    )
    embed.add_field(name="Bot Status", value="✅ Online", inline=True)
    embed.add_field(name="Version", value=APP_VERSION, inline=True)
    embed.add_field(name="Connected Servers", value=str(len(bot.guilds)), inline=True)
    embed.set_footer(text=f"Latency: {round(bot.latency * 1000)}ms")
    await ctx.send(embed=embed)

@bot.command()
async def version(ctx):
    """Show current version"""
    await ctx.send(f"📦 Coin Escape v{APP_VERSION}")

@bot.command()
async def coinflip(ctx):
    """Flip a coin"""
    result = random.choice(["Heads", "Tails"])
    await ctx.send(f"🪙 The coin landed on **{result}**!")

@bot.command()
async def server(ctx):
    """Server info"""
    guild = ctx.guild
    embed = discord.Embed(
        title=f"🛡️ {guild.name}",
        description="Server information:",
        color=0x3498db
    )
    embed.add_field(name="Owner", value=str(guild.owner), inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed)

# ============================================
# EXCHANGE COMMANDS
# ============================================

@bot.command()
async def exchanges(ctx):
    """List supported exchanges"""
    exchanges = "\n".join([f"• {ex}" for ex in SUPPORTED_EXCHANGES])
    embed = discord.Embed(
        title="🏦 Supported Exchanges",
        description=exchanges,
        color=0x3498db
    )
    embed.set_footer(text=f"{len(SUPPORTED_EXCHANGES)} exchanges supported")
    await ctx.send(embed=embed)

# ============================================
# EXCHANGE STATUS SCANNER
# ============================================

@bot.command()
async def exchange_status(ctx, exchange: str = None):
    """Check if an exchange is online (simplified, reliable)"""
    
    if exchange:
        exchange = exchange.lower()
        if exchange == "binance":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.binance.com/api/v3/ping", timeout=5) as resp:
                        if resp.status == 200:
                            await ctx.send("🟢 **Binance** is online!")
                        else:
                            await ctx.send(f"🟡 **Binance** responded with status {resp.status}")
            except asyncio.TimeoutError:
                await ctx.send("🔴 **Binance** is not responding (timeout).")
            except:
                await ctx.send("🔴 **Binance** is offline or not reachable.")
            return
        elif exchange == "bybit":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.bybit.com/v5/system/time", timeout=5) as resp:
                        if resp.status == 200:
                            await ctx.send("🟢 **Bybit** is online!")
                        else:
                            await ctx.send(f"🟡 **Bybit** responded with status {resp.status}")
            except asyncio.TimeoutError:
                await ctx.send("🔴 **Bybit** is not responding (timeout).")
            except:
                await ctx.send("🔴 **Bybit** is offline or not reachable.")
            return
        elif exchange == "coinbase":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.coinbase.com/v2/time", timeout=5) as resp:
                        if resp.status == 200:
                            await ctx.send("🟢 **Coinbase** is online!")
                        else:
                            await ctx.send(f"🟡 **Coinbase** responded with status {resp.status}")
            except asyncio.TimeoutError:
                await ctx.send("🔴 **Coinbase** is not responding (timeout).")
            except:
                await ctx.send("🔴 **Coinbase** is offline or not reachable.")
            return
        else:
            await ctx.send(f"❌ Unknown exchange. Try: `binance`, `bybit`, `coinbase`")
            return
    
    # Show all exchanges
    embed = discord.Embed(
        title="🔌 Exchange Status",
        description="Checking if exchanges are online...",
        color=0x3498db
    )
    
    # Check Binance
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ping", timeout=5) as resp:
                embed.add_field(name="Binance", value="🟢 Online" if resp.status == 200 else "🔴 Offline", inline=True)
    except:
        embed.add_field(name="Binance", value="🔴 Offline", inline=True)
    
    # Check Bybit
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.bybit.com/v5/system/time", timeout=5) as resp:
                embed.add_field(name="Bybit", value="🟢 Online" if resp.status == 200 else "🔴 Offline", inline=True)
    except:
        embed.add_field(name="Bybit", value="🔴 Offline", inline=True)
    
    # Check Coinbase
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coinbase.com/v2/time", timeout=5) as resp:
                embed.add_field(name="Coinbase", value="🟢 Online" if resp.status == 200 else "🔴 Offline", inline=True)
    except:
        embed.add_field(name="Coinbase", value="🔴 Offline", inline=True)
    
    embed.set_footer(text=f"Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    await ctx.send(embed=embed)

# ============================================
# COINS SCANNER (TOP 10 DEPOSIT/WITHDRAW STATUS)
# ============================================

@bot.command()
async def coins(ctx):
    """Check deposit/withdrawal status for top 10 coins"""
    
    # Top 10 coins to check
    coin_list = ["BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX"]
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.binance.com/api/v3/capital/config/getall") as resp:
                if resp.status != 200:
                    await ctx.send("❌ Failed to fetch coin status from Binance.")
                    return
                data = await resp.json()
        except:
            await ctx.send("❌ Error connecting to Binance API.")
            return
    
    # Build the embed
    embed = discord.Embed(
        title="🪙 Binance Coin Status (Top 10)",
        description="Deposit & Withdrawal status for the most popular coins",
        color=0xf0b90b
    )
    
    status_text = ""
    for coin_name in coin_list:
        coin_data = None
        for item in data:
            if item['coin'] == coin_name:
                coin_data = item
                break
        
        if not coin_data:
            status_text += f"**{coin_name}** ❌ No data\n"
            continue
        
        network_list = coin_data.get('networkList', [])
        if not network_list:
            status_text += f"**{coin_name}** ❌ No networks\n"
            continue
        
        # Check if any network has deposit/withdraw enabled
        deposit_enabled = any(n.get('depositEnable', False) for n in network_list)
        withdraw_enabled = any(n.get('withdrawEnable', False) for n in network_list)
        
        deposit_emoji = "✅" if deposit_enabled else "❌"
        withdraw_emoji = "✅" if withdraw_enabled else "❌"
        
        status_text += f"**{coin_name}** {deposit_emoji} Deposit  {withdraw_emoji} Withdraw\n"
    
    embed.add_field(name="Status", value=status_text, inline=False)
    embed.set_footer(text=f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    await ctx.send(embed=embed)

# ============================================
# PRICE COMMANDS
# ============================================

@bot.command()
async def price(ctx, coin: str = "bitcoin"):
    """Get current crypto price (bitcoin, ethereum, solana, etc.)"""
    coin = coin.lower()
    
    # Map common names to CoinGecko IDs
    coin_map = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "ada": "cardano",
        "dot": "polkadot",
        "avax": "avalanche-2",
        "matic": "polygon",
        "link": "chainlink",
        "uni": "uniswap",
        "doge": "dogecoin"
    }
    
    coin_id = coin_map.get(coin, coin)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
            ) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Could not find coin: `{coin}`")
                    return
                data = await resp.json()
                
                if coin_id not in data:
                    await ctx.send(f"❌ Could not find coin: `{coin}`")
                    return
                
                price = data[coin_id]['usd']
                change = data[coin_id].get('usd_24h_change', 0)
                
                emoji = "📈" if change >= 0 else "📉"
                change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                
                embed = discord.Embed(
                    title=f"💰 {coin.upper()} Price",
                    description=f"**${price:,.2f}**",
                    color=0x00ff88 if change >= 0 else 0xff4444
                )
                embed.add_field(name="24h Change", value=f"{emoji} {change_str}", inline=True)
                embed.add_field(name="Source", value="CoinGecko", inline=True)
                embed.set_footer(text=f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                await ctx.send(embed=embed)
    
    except:
        await ctx.send("❌ Error fetching price data. Please try again.")

@bot.command()
async def btc(ctx):
    """Get Bitcoin price"""
    await price(ctx, "bitcoin")

@bot.command()
async def eth(ctx):
    """Get Ethereum price"""
    await price(ctx, "ethereum")

@bot.command()
async def sol(ctx):
    """Get Solana price"""
    await price(ctx, "solana")

# ============================================
# BINANCE NETWORK STATUS (ONE COIN)
# ============================================

@bot.command()
async def withdraw_status(ctx, coin: str = None):
    """Check deposit/withdrawal status for a specific coin (e.g., !withdraw-status BTC)"""
    
    if not coin:
        await ctx.send("❌ Please specify a coin. Example: `!withdraw-status BTC` or `!withdraw-status ETH`")
        return
    
    coin = coin.upper()
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.binance.com/api/v3/capital/config/getall") as resp:
                if resp.status != 200:
                    await ctx.send("❌ Failed to fetch network status from Binance.")
                    return
                data = await resp.json()
        except:
            await ctx.send("❌ Error connecting to Binance API.")
            return
    
    # Find the coin
    coin_data = None
    for item in data:
        if item['coin'] == coin:
            coin_data = item
            break
    
    if not coin_data:
        await ctx.send(f"❌ No network information found for **{coin}**. Please check the symbol (e.g., BTC, ETH, SOL).")
        return
    
    # Build the embed
    embed = discord.Embed(
        title=f"🌐 {coin} Network Status",
        description=f"Deposit & Withdrawal status for **{coin}**",
        color=0xf0b90b
    )
    
    network_list = coin_data.get('networkList', [])
    
    if not network_list:
        embed.add_field(name="⚠️ No networks available", value="No network data found for this coin.", inline=False)
    else:
        for network in network_list[:10]:
            network_name = network.get('network', 'Unknown')
            deposit = network.get('depositEnable', False)
            withdraw = network.get('withdrawEnable', False)
            
            deposit_emoji = "✅" if deposit else "❌"
            withdraw_emoji = "✅" if withdraw else "❌"
            
            status_text = f"**Deposit:** {deposit_emoji} | **Withdraw:** {withdraw_emoji}"
            
            min_confirm = network.get('minConfirm', 'N/A')
            if min_confirm != 'N/A':
                status_text += f"\n`Confirmations: {min_confirm}`"
            
            embed.add_field(
                name=f"**{network_name}**",
                value=status_text,
                inline=False
            )
    
    embed.set_footer(text=f"Data provided by Binance | Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    await ctx.send(embed=embed)

# ============================================
# ADVANCED TRANSACTION TRACKING (with API keys)
# ============================================

@bot.command()
async def track(ctx, network: str, txid: str):
    """Track ANY transaction on Solana, Ethereum, BSC, Bitcoin, etc.
    Usage: !track SOL 5W... or !track ETH 0x..."""
    
    network = network.lower()
    
    # Build explorer URLs with API keys from environment
    explorers = {
        "sol": {
            "name": "Solana",
            "url": f"https://api.solscan.io/v1/transaction/{txid}",
            "view": f"https://solscan.io/tx/{txid}",
            "type": "solscan"
        },
        "eth": {
            "name": "Ethereum",
            "url": f"https://api.etherscan.io/api?module=transaction&action=gettxreceiptstatus&txhash={txid}&apikey={ETHERSCAN_KEY}",
            "view": f"https://etherscan.io/tx/{txid}",
            "type": "etherscan"
        },
        "bsc": {
            "name": "BNB Smart Chain",
            "url": f"https://api.bscscan.com/api?module=transaction&action=gettxreceiptstatus&txhash={txid}&apikey={BSCSCAN_KEY}",
            "view": f"https://bscscan.com/tx/{txid}",
            "type": "bscscan"
        },
        "btc": {
            "name": "Bitcoin",
            "url": f"https://blockchain.info/rawtx/{txid}",
            "view": f"https://www.blockchain.com/explorer/transactions/btc/{txid}",
            "type": "blockchain"
        }
    }
    
    if network not in explorers:
        networks_list = "\n".join([f"• {key.upper()}" for key in explorers.keys()])
        await ctx.send(f"❌ Unknown network. Available:\n{networks_list}")
        return
    
    explorer = explorers[network]
    
    # Show initial loading message
    loading_msg = await ctx.send(f"🔍 Searching **{explorer['name']}** for transaction...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(explorer['url']) as resp:
                if resp.status != 200:
                    await loading_msg.edit(content=f"❌ Transaction not found on {explorer['name']}. Check the TXID and try again.")
                    return
                data = await resp.json()
        
        # Different parsing logic for each explorer
        if explorer['type'] == "solscan":
            # Solana
            if not data or data.get('success') == False:
                await loading_msg.edit(content=f"❌ Transaction not found on Solana.")
                return
            tx_data = data.get('data', {})
            status = "✅ SUCCESS" if tx_data.get('status') == 'success' else "❌ FAILED"
            amount = tx_data.get('lamports', 0) / 1e9
            timestamp = datetime.fromtimestamp(tx_data.get('blockTime', 0)).strftime('%Y-%m-%d %H:%M:%S UTC')
            confirmations = "N/A"
            from_addr = tx_data.get('from', 'N/A')
            to_addr = tx_data.get('to', 'N/A')
            fee = tx_data.get('fee', 0) / 1e9
            
            embed = discord.Embed(
                title=f"🔍 Solana Transaction",
                description=f"Status: {status}",
                color=0x00ff88 if "SUCCESS" in status else 0xff4444
            )
            embed.add_field(name="💰 Amount", value=f"{amount:.4f} SOL", inline=True)
            embed.add_field(name="⏱️ Time", value=timestamp, inline=True)
            embed.add_field(name="✅ Confirmations", value=confirmations, inline=True)
            embed.add_field(name="📤 From", value=f"`{from_addr[:8]}...{from_addr[-8:]}`", inline=False)
            embed.add_field(name="📥 To", value=f"`{to_addr[:8]}...{to_addr[-8:]}`", inline=False)
            embed.add_field(name="⛽ Fee", value=f"{fee:.6f} SOL", inline=True)
            embed.add_field(name="🔗 Explorer", value=f"[View on Solscan]({explorer['view']})", inline=False)
            embed.set_footer(text=f"TXID: {txid[:16]}...")
            
        elif explorer['type'] == "blockchain":
            # Bitcoin
            if not data:
                await loading_msg.edit(content=f"❌ Transaction not found on Bitcoin.")
                return
            
            status = "✅ SUCCESS"
            amount = sum([out.get('value', 0) for out in data.get('out', [])]) / 1e8
            timestamp = datetime.fromtimestamp(data.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S UTC')
            confirmations = data.get('block_height', 'N/A')
            fee = data.get('fee', 0) / 1e8
            
            embed = discord.Embed(
                title=f"🔍 Bitcoin Transaction",
                description=f"Status: {status}",
                color=0x00ff88
            )
            embed.add_field(name="💰 Amount", value=f"{amount:.8f} BTC", inline=True)
            embed.add_field(name="⏱️ Time", value=timestamp, inline=True)
            embed.add_field(name="✅ Confirmations", value=confirmations, inline=True)
            embed.add_field(name="⛽ Fee", value=f"{fee:.8f} BTC", inline=True)
            embed.add_field(name="🔗 Explorer", value=f"[View on Blockchain.com]({explorer['view']})", inline=False)
            embed.set_footer(text=f"TXID: {txid[:16]}...")
        
        else:
            # Ethereum / BSC - Simplified (requires API key)
            embed = discord.Embed(
                title=f"🔍 {explorer['name']} Transaction",
                description="Click the link below to view full details on the explorer.",
                color=0x3498db
            )
            embed.add_field(name="🔗 View on Explorer", value=f"[Click here to view]({explorer['view']})", inline=False)
            embed.set_footer(text=f"TXID: {txid[:16]}...")
        
        await loading_msg.edit(content=None, embed=embed)
    
    except Exception as e:
        await loading_msg.edit(content=f"❌ Error fetching transaction: {str(e)}")

# ============================================
# SUPPORT COMMAND
# ============================================

@bot.command()
async def support(ctx, withdrawal_id: str = None):
    """Get direct Binance support link for a withdrawal"""
    
    if not withdrawal_id:
        # Show general support links
        embed = discord.Embed(
            title="🆘 Binance Withdrawal Support",
            description="Need help with a withdrawal? Here are the official support links:",
            color=0xf0b90b
        )
        embed.add_field(
            name="📧 Binance Support Center",
            value="[Open Support Ticket](https://www.binance.com/en/support/ticket)\n\n"
                  "**Before contacting support, please check:**\n"
                  "• Network status with `!withdraw-status BTC`\n"
                  "• Your withdrawal status in Binance app\n"
                  "• If you have the TXID, use `!track`",
            inline=False
        )
        embed.add_field(
            name="📊 Common Withdrawal Issues",
            value="• **Pending**: Wait for confirmations\n"
                  "• **Failed**: Check network status\n"
                  "• **Delayed**: Network congestion\n"
                  "• **Wrong network**: Contact support immediately",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Support link with withdrawal ID
    support_url = f"https://www.binance.com/en/support/ticket?withdrawal_id={withdrawal_id}"
    
    embed = discord.Embed(
        title="🆘 Withdrawal Support",
        description=f"Direct support link for Withdrawal ID: **{withdrawal_id}**",
        color=0xf0b90b
    )
    embed.add_field(
        name="🔗 Open Support Ticket",
        value=f"[Click here to contact Binance Support]({support_url})\n\n"
              "**Have this information ready:**\n"
              "• Withdrawal ID\n"
              "• Amount and coin\n"
              "• Timestamp of withdrawal\n"
              "• Transaction hash (if available)",
        inline=False
    )
    embed.set_footer(text="🚨 Contact support immediately for any issues with your funds.")
    
    await ctx.send(embed=embed)

# ============================================
# TWITTER/X FUD & NEWS COMMANDS (VIP/Admin only)
# ============================================

@bot.command()
async def fud(ctx):
    """Manually check for recent EXCHANGE FUD / large withdrawal tweets."""
    if not has_permission(ctx):
        await ctx.send("❌ You need the **VIP** or **Admin** role to use this command.")
        return

    if not TWITTER_CLIENT:
        await ctx.send("❌ Twitter API not configured. Please set BEARER_TOKEN in .env.")
        return

    await ctx.send("🔍 Scanning Twitter for exchange FUD and large withdrawals...")
    alerts = await get_twitter_alerts(category="exchange")
    if not alerts:
        await ctx.send("✅ No new exchange FUD or large withdrawal tweets in the last 24 hours.")
        return
    embed = discord.Embed(
        title="🚨 Exchange FUD & Large Withdrawal Alerts",
        description=f"Found **{len(alerts)}** exchange-related alerts:",
        color=0xff5500,
        timestamp=datetime.utcnow()
    )
    for alert in alerts[:10]:
        embed.add_field(
            name=f"{alert['detail']}",
            value=f"{alert['text']}... [Link]({alert['url']})",
            inline=False
        )
    if len(alerts) > 10:
        embed.set_footer(text=f"Showing first 10 of {len(alerts)} alerts")
    await ctx.send(embed=embed)

@bot.command()
async def news(ctx):
    """Manually check for broader crypto news / FUD tweets (non-exchange)."""
    if not has_permission(ctx):
        await ctx.send("❌ You need the **VIP** or **Admin** role to use this command.")
        return

    if not TWITTER_CLIENT:
        await ctx.send("❌ Twitter API not configured. Please set BEARER_TOKEN.")
        return

    await ctx.send("📰 Scanning Twitter for general crypto news and FUD...")
    alerts = await get_twitter_alerts(category="news")
    if not alerts:
        await ctx.send("✅ No new crypto news tweets in the last 24 hours.")
        return
    embed = discord.Embed(
        title="📰 Crypto News & Market FUD",
        description=f"Found **{len(alerts)}** news items:",
        color=0x3498db,
        timestamp=datetime.utcnow()
    )
    for alert in alerts[:10]:
        embed.add_field(
            name=f"{alert['detail']}",
            value=f"{alert['text']}... [Link]({alert['url']})",
            inline=False
        )
    if len(alerts) > 10:
        embed.set_footer(text=f"Showing first 10 of {len(alerts)} alerts")
    await ctx.send(embed=embed)

@bot.command()
async def fud_status(ctx):
    """Show status of the FUD alert system."""
    if not has_permission(ctx):
        await ctx.send("❌ You need the **VIP** or **Admin** role to use this command.")
        return

    embed = discord.Embed(
        title="📊 FUD Alert System Status",
        color=0x3498db
    )
    if fud_last_run:
        embed.add_field(
            name="Last Auto-Run",
            value=f"{fud_last_run.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            inline=False
        )
        embed.add_field(
            name="Tweets Found (last run)",
            value=str(fud_last_count),
            inline=True
        )
    else:
        embed.add_field(
            name="Status",
            value="No auto-run has occurred yet.",
            inline=False
        )
    embed.add_field(name="Auto-Interval", value="Every 24 hours", inline=True)
    embed.add_field(name="Manual Command", value="!fud", inline=True)
    embed.add_field(
        name="Twitter Client",
        value="✅ Configured" if TWITTER_CLIENT else "❌ Not Configured",
        inline=True
    )
    embed.set_footer(text="processed_tweets.json tracks seen tweets")
    await ctx.send(embed=embed)

@bot.command()
async def test_twitter(ctx):
    """Test if Twitter API returns any tweets."""
    if not has_permission(ctx):
        await ctx.send("❌ You need the **VIP** or **Admin** role to use this command.")
        return

    if not TWITTER_CLIENT:
        await ctx.send("❌ Twitter client not configured. Please set BEARER_TOKEN in .env.")
        return
    try:
        tweets = TWITTER_CLIENT.search_recent_tweets(
            query="crypto",
            max_results=10
        )
        count = len(tweets.data) if tweets.data else 0
        if count > 0:
            await ctx.send(f"✅ Twitter API is working! Found {count} tweets about 'crypto'.\nExample: {tweets.data[0].text[:100]}...")
        else:
            await ctx.send("⚠️ API returned 0 tweets. Check your Bearer Token permissions.")
    except Exception as e:
        await ctx.send(f"❌ Twitter API error: {e}")

@bot.command()
async def fud_debug(ctx):
    """Debug: show raw tweets from the FUD query without filtering."""
    if not has_permission(ctx):
        await ctx.send("❌ You need the **VIP** or **Admin** role to use this command.")
        return

    if not TWITTER_CLIENT:
        await ctx.send("❌ Twitter client not configured. Please set BEARER_TOKEN in .env.")
        return
    await ctx.send("🔍 Fetching raw tweets with the FUD query...")
    # Fixed: removed invalid '*' wildcard
    query = (
        "(binance OR coinbase OR kraken OR bybit OR ftx OR okx OR huobi OR kucoin OR gate.io OR crypto.com OR exchange) "
        "AND (withdraw OR outflow OR deposit OR transfer OR fud OR panic OR bank run OR insolvent OR freeze OR halt OR collapse OR hack OR scam OR rug OR crash OR \"can't withdraw\" OR \"withdrawal issue\") "
        "-is:retweet -is:reply lang:en"
    )
    end_time = datetime.utcnow() - timedelta(seconds=30)
    start_time = end_time - timedelta(hours=24)
    try:
        tweets = TWITTER_CLIENT.search_recent_tweets(
            query=query,
            tweet_fields=["created_at", "author_id"],
            max_results=10,
            start_time=start_time.isoformat(timespec="seconds") + "Z",
            end_time=end_time.isoformat(timespec="seconds") + "Z"
        )
        count = len(tweets.data) if tweets.data else 0
        if count > 0:
            sample = tweets.data[0].text[:150] + "..."
            await ctx.send(f"✅ Found {count} tweets. Sample: {sample}")
        else:
            await ctx.send(f"⚠️ Zero tweets found for the FUD query in the last 24 hours.\n"
                          f"Check if there's actually any talk – try a simpler query like `(crypto)`.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ============================================
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: No Discord token found! Create a .env file with DISCORD_TOKEN=your_token")
    else:
        print("🚀 Starting Coin Escape Bot v2.1...")
        bot.run(TOKEN)
