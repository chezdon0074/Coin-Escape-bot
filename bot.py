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

# Remove the default help command so we can use our own
bot.remove_command('help')

# Bot info
APP_VERSION = "2.1.0"
SUPPORTED_EXCHANGES = ["Binance", "Bybit", "Coinbase", "Kraken", "KuCoin", "OKX", "Hyperliquid"]

# ============================================
# BACKGROUND TASKS (AUTO-ALERTS)
# ============================================

@tasks.loop(minutes=5)
async def check_exchange_status_auto():
    """Auto-check exchange status every 5 minutes with alerts"""
    channel_id = os.getenv('ALERT_CHANNEL_ID')
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    
    # Check Binance
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
    check_exchange_status_auto.start()
    send_daily_report.start()
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="crypto markets | !help"
    ))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.CommandNotFound):
        await ctx.send(f"❌ Unknown command. Type `!help` for available commands.")
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"Error: {error}")

# ============================================
# BASIC COMMANDS
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
# HELP COMMAND (fixed conflict with built-in help)
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
        value="`!exchange-status` - Check if exchanges are online\n"
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
              "`!support` - Binance support links",
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
# SIMPLIFIED & RELIABLE EXCHANGE STATUS SCANNER
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
# BINANCE NETWORK STATUS (Deposit/Withdrawal)
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
# ADVANCED TRANSACTION TRACKING
# ============================================

@bot.command()
async def track(ctx, network: str, txid: str):
    """Track ANY transaction on Solana, Ethereum, BSC, Bitcoin, etc.
    Usage: !track SOL 5W... or !track ETH 0x..."""
    
    network = network.lower()
    
    # Network configurations
    explorers = {
        "sol": {
            "name": "Solana",
            "url": f"https://api.solscan.io/v1/transaction/{txid}",
            "view": f"https://solscan.io/tx/{txid}",
            "type": "solscan"
        },
        "eth": {
            "name": "Ethereum",
            "url": f"https://api.etherscan.io/api?module=transaction&action=gettxreceiptstatus&txhash={txid}&apikey=YourEtherscanKey",
            "view": f"https://etherscan.io/tx/{txid}",
            "type": "etherscan"
        },
        "bsc": {
            "name": "BNB Smart Chain",
            "url": f"https://api.bscscan.com/api?module=transaction&action=gettxreceiptstatus&txhash={txid}&apikey=YourBscScanKey",
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
            # Ethereum / BSC - Simplified
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
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: No token found! Create a .env file with DISCORD_TOKEN=your_token")
    else:
        print("🚀 Starting Coin Escape Bot v2.1...")
        bot.run(TOKEN)
