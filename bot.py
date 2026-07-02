import discord
from discord.ext import commands, tasks
import os
import random
import aiohttp
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot configuration
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Bot info
APP_VERSION = "2.0.0"
SUPPORTED_EXCHANGES = ["Binance", "Bybit", "Coinbase", "Kraken", "KuCoin", "OKX", "Deribit"]

# ============================================
# BACKGROUND TASKS (AUTO-ALERTS)
# ============================================

@tasks.loop(minutes=5)
async def check_exchange_status():
    """Check exchange status every 5 minutes"""
    channel_id = os.getenv('ALERT_CHANNEL_ID')  # Set this in .env
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    
    # Check Binance
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ping") as resp:
                if resp.status == 200:
                    status = "🟢 Online"
                else:
                    status = "🔴 Offline"
                    await channel.send(f"⚠️ **ALERT:** Binance is having issues! Status: {resp.status}")
    except:
        await channel.send("🔴 **ALERT:** Binance is not responding!")
    
    # Add more exchanges here

@tasks.loop(hours=1)
async def send_daily_report():
    """Send a daily report every hour"""
    channel_id = os.getenv('ALERT_CHANNEL_ID')
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    
    # Get Bitcoin price
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as resp:
                data = await resp.json()
                btc_price = data.get('bitcoin', {}).get('usd', 'N/A')
                await channel.send(f"📊 **Daily Report**\nBitcoin: ${btc_price}\nAll systems operational")
    except:
        await channel.send("⚠️ Could not fetch price data")

# ============================================
# EVENTS
# ============================================

@bot.event
async def on_ready():
    print(f'✅ Coin Escape Bot is online!')
    print(f'📊 Logged in as: {bot.user}')
    print(f'🌐 Connected to {len(bot.guilds)} servers')
    
    # Start background tasks
    check_exchange_status.start()
    send_daily_report.start()
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="crypto markets | !help"
    ))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Unknown command. Type `!commands` for available commands.")
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"Error: {error}")

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

@bot.command()
async def exchange_status(ctx, exchange: str = None):
    """Check if an exchange is online"""
    if not exchange:
        embed = discord.Embed(
            title="🔌 Exchange Status",
            description="Checking all exchanges...",
            color=0x3498db
        )
        
        # Check Binance
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.binance.com/api/v3/ping") as resp:
                    status = "🟢 Online" if resp.status == 200 else "🔴 Offline"
                    embed.add_field(name="Binance", value=status, inline=True)
        except:
            embed.add_field(name="Binance", value="🔴 Offline", inline=True)
        
        # Check Bybit
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.bybit.com/v5/system/time") as resp:
                    status = "🟢 Online" if resp.status == 200 else "🔴 Offline"
                    embed.add_field(name="Bybit", value=status, inline=True)
        except:
            embed.add_field(name="Bybit", value="🔴 Offline", inline=True)
        
        # Check Coinbase
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.coinbase.com/v2/time") as resp:
                    status = "🟢 Online" if resp.status == 200 else "🔴 Offline"
                    embed.add_field(name="Coinbase", value=status, inline=True)
        except:
            embed.add_field(name="Coinbase", value="🔴 Offline", inline=True)
        
        embed.set_footer(text=f"Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.send(embed=embed)
        return
    
    # Check specific exchange
    exchange = exchange.lower()
    if exchange == "binance":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.binance.com/api/v3/ping") as resp:
                    if resp.status == 200:
                        await ctx.send(f"🟢 **Binance** is online!")
                    else:
                        await ctx.send(f"🔴 **Binance** is offline (Status: {resp.status})")
        except:
            await ctx.send("🔴 **Binance** is not responding!")
    
    elif exchange == "bybit":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.bybit.com/v5/system/time") as resp:
                    if resp.status == 200:
                        await ctx.send(f"🟢 **Bybit** is online!")
                    else:
                        await ctx.send(f"🔴 **Bybit** is offline (Status: {resp.status})")
        except:
            await ctx.send("🔴 **Bybit** is not responding!")
    
    elif exchange == "coinbase":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.coinbase.com/v2/time") as resp:
                    if resp.status == 200:
                        await ctx.send(f"🟢 **Coinbase** is online!")
                    else:
                        await ctx.send(f"🔴 **Coinbase** is offline (Status: {resp.status})")
        except:
            await ctx.send("🔴 **Coinbase** is not responding!")
    
    else:
        await ctx.send(f"❌ Unknown exchange. Available: `binance`, `bybit`, `coinbase`")

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
# AUTOMATION FEATURES (Coin Escape Integration)
# ============================================

@bot.command()
async def register(ctx):
    """Register your account with Coin Escape"""
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000/api')
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{backend_url}/users/register",
                json={"discord_id": str(ctx.author.id), "discord_username": ctx.author.name}
            ) as resp:
                if resp.status == 200:
                    await ctx.send(f"✅ Registered {ctx.author.mention}! Welcome to Coin Escape! 🎉")
                else:
                    await ctx.send("❌ Registration failed. Please try again.")
    except:
        await ctx.send("❌ Backend is not running! Start the backend first.")

@bot.command()
async def balance(ctx):
    """Check your Coin Escape balance"""
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000/api')
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{backend_url}/users/{ctx.author.id}/balance") as resp:
                if resp.status == 404:
                    await ctx.send("❌ You haven't registered yet! Use `!register`")
                    return
                data = await resp.json()
                
                embed = discord.Embed(
                    title=f"💰 {ctx.author.name}'s Balance",
                    color=0x00ff88
                )
                embed.add_field(name="Total Balance", value=f"${data['total_balance']:,.2f}", inline=False)
                
                if data['exchanges']:
                    exchange_text = ""
                    for exchange, balance in data['exchanges'].items():
                        exchange_text += f"• {exchange.upper()}: ${balance:,.2f}\n"
                    embed.add_field(name="Exchange Balances", value=exchange_text, inline=False)
                else:
                    embed.add_field(name="No exchanges connected", value="Connect exchanges in the mobile app", inline=False)
                
                await ctx.send(embed=embed)
    except:
        await ctx.send("❌ Backend is not running! Start the backend first.")

# ============================================
# BASIC COMMANDS (Keep existing)
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

@bot.command()
async def commands(ctx):
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
              "`!commands` - Show this menu",
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
        value="`!exchange-status` - Check exchange health\n"
              "`!price <coin>` - Get crypto price\n"
              "`!btc` - Bitcoin price\n"
              "`!eth` - Ethereum price\n"
              "`!sol` - Solana price",
        inline=False
    )
    embed.add_field(
        name="🎮 Coin Escape (Requires Backend)",
        value="`!register` - Create your account\n"
              "`!balance` - Check your balance",
        inline=False
    )
    embed.set_footer(text="🔄 Automation features active")
    await ctx.send(embed=embed)

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
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: No token found! Create a .env file with DISCORD_TOKEN=your_token")
    else:
        print("🚀 Starting Coin Escape Bot v2.0...")
        bot.run(TOKEN)
