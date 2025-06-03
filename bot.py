import os
import asyncio
import aiohttp
import base64
import logging
import uuid
from io import BytesIO
from typing import Optional, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Model configurations
MODELS = {
    "flux": {"id": "runware:101@1", "name": "FLUX Dev", "supports_reference": False},
    "hidream": {"id": "runware:97@2", "name": "HiDream Pro", "supports_reference": False},
    "kontext": {"id": "bfl:3@1", "name": "Kontext Pro", "supports_reference": True},
    "kontext-max": {"id": "bfl:4@1", "name": "Kontext Max", "supports_reference": True},
    "fast": {"id": "runware:100@1", "name": "FLUX Schnell", "supports_reference": False}
}

class ImageBot:
    def __init__(self):
        self.api_key = os.getenv("RUNWARE_API_KEY")
        self.api_url = "https://api.runware.ai/v1"

    def get_dimensions(self, model_id: str, orientation: str = "portrait") -> tuple:
        """Get width and height based on model and orientation"""
        if orientation.lower() == "square":
            return 1024, 1024  # Square: width = height
        elif "bfl" in model_id:  # Kontext
            if orientation.lower() == "landscape":
                return 1392, 752  # Landscape: width > height
            else:
                return 752, 1392  # Portrait: height > width
        else:  # FLUX and HiDream
            if orientation.lower() == "landscape":
                return 1344, 704  # Landscape: width > height
            else:
                return 704, 1344  # Portrait: height > width

    async def generate_image(self, prompt: str, model_id: str, orientation: str = "portrait", reference_image_base64: Optional[str] = None) -> Optional[str]:
        """Generate image using Runware HTTP API"""
        try:
            # Generate a unique task UUID
            task_uuid = str(uuid.uuid4())

            # Get dimensions based on model and orientation
            width, height = self.get_dimensions(model_id, orientation)

            # Prepare the payload
            payload = [
                {
                    "taskType": "authentication",
                    "apiKey": self.api_key
                },
                {
                    "taskType": "imageInference",
                    "taskUUID": task_uuid,
                    "positivePrompt": prompt,
                    "width": width,
                    "height": height,
                    "model": model_id,
                    "outputFormat": "JPEG",
                    "includeCost": True,
                    "outputType": ["URL"],
                    "numberResults": 1
                }
            ]

            # Add reference image as raw base64 (not data URI)
            if reference_image_base64 and "bfl" in model_id:
                payload[1]["referenceImages"] = [reference_image_base64]

            # Make the HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:

                    if response.status != 200:
                        logger.error(f"API request failed with status {response.status}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text}")
                        return None

                    result = await response.json()
                    logger.info(f"API Response: {result}")

                    # Check for errors in the response
                    if isinstance(result, list):
                        for item in result:
                            if "error" in item:
                                logger.error(f"API returned error: {item['error']}")
                                return None
                    elif "error" in result:
                        logger.error(f"API returned error: {result['error']}")
                        return None

                    # Extract image URL from response
                    items_to_check = result if isinstance(result, list) else result.get("data", [])

                    for item in items_to_check:
                        if (item.get("taskType") == "imageInference" and 
                            item.get("taskUUID") == task_uuid and 
                            "imageURL" in item):
                            image_url = item.get("imageURL")
                            if image_url:
                                # Download the image and convert to base64
                                return await self.download_image_as_base64(image_url)

                    logger.error("No image URL found in API response")
                    logger.error(f"Full response: {result}")
                    return None

        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None

    async def download_image_as_base64(self, image_url: str) -> Optional[str]:
        """Download image from URL and convert to base64"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        content = await response.read()
                        return base64.b64encode(content).decode('utf-8')
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def upload_telegram_image(self, file_id: str, bot) -> Optional[str]:
        """Upload Telegram image and return raw base64"""
        try:
            # Get file from Telegram
            file = await bot.get_file(file_id)

            # Download file content
            async with aiohttp.ClientSession() as session:
                async with session.get(file.file_path) as response:
                    if response.status == 200:
                        content = await response.read()
                        # Return raw base64 string
                        image_base64 = base64.b64encode(content).decode('utf-8')
                        return image_base64

            return None
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None

# Initialize bot instance
image_bot = ImageBot()

def parse_command_args(args: List[str]) -> tuple:
    """Parse command arguments to extract orientation, number of images, and prompt"""
    orientation = "portrait"  # default
    num_images = 1  # default
    use_max = False  # default
    prompt_args = args.copy()

    i = 0
    while i < len(prompt_args):
        arg = prompt_args[i].lower()
        if arg in ['--landscape', '-l']:
            orientation = "landscape"
            prompt_args.pop(i)
            # Don't increment i since we removed an item
        elif arg in ['--portrait', '-p']:
            orientation = "portrait"
            prompt_args.pop(i)
            # Don't increment i since we removed an item
        elif arg in ['--square', '-s']:
            orientation = "square"
            prompt_args.pop(i)
            # Don't increment i since we removed an item
        elif arg in ['--max', '-max']:
            use_max = True
            prompt_args.pop(i)
            # Don't increment i since we removed an item
        elif arg == '-n' and i + 1 < len(prompt_args):
            try:
                num_images = int(prompt_args[i + 1])
                if num_images < 1:
                    num_images = 1
                elif num_images > 10:  # Limit to 10 images max
                    num_images = 10
                prompt_args.pop(i)  # Remove -n
                prompt_args.pop(i)  # Remove the number (now at index i)
                # Don't increment i since we removed two items
            except (ValueError, IndexError):
                # If conversion fails or index is out of range, skip this argument
                i += 1
        else:
            i += 1

    prompt = " ".join(prompt_args)
    return orientation, num_images, use_max, prompt

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🦑 **Cuttlefish**

I can generate amazing images using different AI models:

🔥 **FLUX Big** - High quality general purpose model
🌟 **HiDream** - Artistic and dreamy style
✨ **Kontext Pro** - Can edit existing images with reference

**Commands:**
• `/flux <prompt>` - Generate with FLUX Big
• `/hidream <prompt>` - Generate with HiDream
• `/kontext <prompt>` - Generate with Kontext Pro

**Orientation Options:**
Add `--landscape` or `-l` for landscape orientation
Add `--portrait` or `-p` for portrait orientation (default)

**Examples:**
• `/flux a beautiful sunset` (portrait)
• `/flux --landscape a beautiful sunset` (landscape)
• `/hidream -l cyberpunk city` (landscape)

**For image editing with Kontext:**
Send an image with a caption describing the changes you want to make!

Example: Send a photo with caption "Turn this into a pencil sketch"
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def generate_flux(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image with FLUX model"""
    await generate_image_direct(update, context, "flux")

async def generate_hidream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image with HiDream model"""
    await generate_image_direct(update, context, "hidream")

async def generate_kontext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image with Kontext model"""
    await generate_image_direct(update, context, "kontext")

async def generate_fast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image with FLUX Fast model"""
    await generate_image_direct(update, context, "fast")

async def generate_image_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, model_key: str):
    """Generate image directly with specified model"""
    if not context.args:
        await update.message.reply_text(
            f"Please provide a prompt! Examples:\n"
            f"• `/{model_key} a beautiful sunset` (portrait)\n"
            f"• `/{model_key} --landscape a beautiful sunset` (landscape)\n"
            f"• `/{model_key} --square a beautiful sunset` (square)\n"
            f"• `/{model_key} -n 3 -s a beautiful sunset` (generate 3 square images)",
            parse_mode='Markdown'
        )
        return

    # Parse orientation, number of images, and prompt
    orientation, num_images, use_max, prompt = parse_command_args(context.args)

    if not prompt:
        await update.message.reply_text(
            f"Please provide a prompt after the options!\n"
            f"Example: `/{model_key} --landscape -n 2 a beautiful sunset`",
            parse_mode='Markdown'
        )
        return

    model = MODELS[model_key]

    # Send generating message with orientation and number info
    orientation_text = "🖼️ Landscape" if orientation == "landscape" else "📱 Portrait" if orientation == "portrait" else "⬛ Square"
    num_text = f"{num_images} images" if num_images > 1 else "1 image"
    generating_msg = await update.message.reply_text(
        f"🎨 Generating {num_text} in {orientation_text} with {model['name']}...\n*Prompt:* {prompt}", 
        parse_mode='Markdown'
    )

    try:
        # Generate multiple images
        for i in range(num_images):
            image_base64 = await image_bot.generate_image(prompt, model["id"], orientation)

            if image_base64:
                # Convert base64 to bytes and send
                image_bytes = base64.b64decode(image_base64)
                caption = f"🎨 Generated with {model['name']} ({orientation_text})\n*Prompt:* {prompt}"
                if num_images > 1:
                    caption += f"\n*Image {i+1} of {num_images}*"
                await update.message.reply_photo(
                    photo=BytesIO(image_bytes),
                    caption=caption,
                    parse_mode='Markdown'
                )
            else:
                await generating_msg.edit_text("❌ Failed to generate image. Please try again.")
                return

        await generating_msg.delete()

    except Exception as e:
        logger.error(f"Error in generate_image_direct: {e}")
        await generating_msg.edit_text("❌ An error occurred while generating the image.")

async def handle_photo_with_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo with caption for image editing using Kontext"""
    if not update.message.photo or not update.message.caption:
        return

    caption = update.message.caption.strip()
    if not caption:
        await update.message.reply_text("Please provide a caption describing what changes you want to make to the image.")
        return

    # Parse orientation, number of images, and prompt from caption
    caption_args = caption.split()
    orientation, num_images, use_max, prompt = parse_command_args(caption_args)

    if not prompt:
        prompt = caption  # Use original caption if no parsing found
        orientation = "portrait"  # Default orientation
        num_images = 1  # Default number of images
        use_max = False  # Default model

    # Select model based on -max flag
    model_key = "kontext-max" if use_max else "kontext"
    model = MODELS[model_key]

    # Send processing message with number and orientation info
    orientation_text = "🖼️ Landscape" if orientation == "landscape" else "📱 Portrait" if orientation == "portrait" else "⬛ Square"
    num_text = f"{num_images} images" if num_images > 1 else "1 image"
    processing_msg = await update.message.reply_text(
        f"🔄 Processing your image to generate {num_text} for {orientation_text} editing with {model['name']}..."
    )

    try:
        # Get the largest photo
        photo = update.message.photo[-1]

        # Upload image and get raw base64
        reference_image_base64 = await image_bot.upload_telegram_image(photo.file_id, context.bot)

        if not reference_image_base64:
            await processing_msg.edit_text("❌ Failed to process the reference image.")
            return

        # Update processing message
        await processing_msg.edit_text(
            f"🎨 Editing image with {model['name']} ({orientation_text})...\n*Changes:* {prompt}\n*Generating {num_text}...*",
            parse_mode='Markdown'
        )

        # Generate multiple edited images
        for i in range(num_images):
            image_base64 = await image_bot.generate_image(prompt, MODELS[model_key]["id"], orientation, reference_image_base64)

            if image_base64:
                # Convert base64 to bytes and send
                image_bytes = base64.b64decode(image_base64)
                caption_text = f"✨ Edited with {model['name']} ({orientation_text})\n**Changes:** {prompt}"
                if num_images > 1:
                    caption_text += f"\n*Image {i+1} of {num_images}*"

                await update.message.reply_photo(
                    photo=BytesIO(image_bytes),
                    caption=caption_text,
                    parse_mode='Markdown'
                )
            else:
                await processing_msg.edit_text("❌ Failed to edit image. Please try again.")
                return

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error in handle_photo_with_caption: {e}")
        await processing_msg.edit_text("❌ An error occurred while editing the image.")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages"""
    text = update.message.text.strip()
    if text and not text.startswith('/'):
        await update.message.reply_text(
            "🦑 **Cuttlefish**\n\n"
            "💡 To generate an image, use:\n"
            "• `/flux <prompt>` - Use FLUX Dev\n"
            "• `/hidream <prompt>` - Use HiDream Pro\n"
            "• `/kontext <prompt>` - Use Kontext Pro\n"
            "• `/fast <prompt>` - Use FLUX Schnell\n\n"
            "**Options:**\n"
            "• Add `--landscape` or `-l` for landscape\n"
            "• Add `--portrait` or `-p` for portrait (default)\n"
            "• Add `--square` or `-s` for square (1024x1024)\n"
            "• Add `-n <number>` to generate multiple images (max 10)\n\n"
            "**Examples:**\n"
            "• `/flux --landscape -n 2 a sunset` (2 landscape images)\n"
            "• `/flux -s a sunset` (square image)\n\n"
            "Or send an image with a caption to edit it! Example: `-s -n 3 -max Turn this into a pencil sketch`. The `-max` option uses kontext max.",
            parse_mode='Markdown'
        )

def main():
    """Main function to run the bot"""
    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    runware_api_key = os.getenv("RUNWARE_API_KEY")
    if not runware_api_key:
        raise ValueError("RUNWARE_API_KEY environment variable is required")

    # Create application
    application = Application.builder().token(bot_token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("flux", generate_flux))
    application.add_handler(CommandHandler("hidream", generate_hidream))
    application.add_handler(CommandHandler("kontext", generate_kontext))
    application.add_handler(CommandHandler("fast", generate_fast))
    application.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, handle_photo_with_caption))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()