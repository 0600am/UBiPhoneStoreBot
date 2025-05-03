import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
# telegram.helpers contains escape_markdown in v20+
from telegram.helpers import escape_markdown
# Import error types for more specific handling if needed
from telegram.error import TelegramError

from flask import Flask
from threading import Thread

# --- Configuration ---
# Ensure these are set in your environment (e.g., Codespaces Secrets)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Added format for better logs
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load products safely
PRODUCTS = []
try:
    # Ensure the file is in the same directory or provide the correct path
    with open("products.json", "r", encoding="utf-8") as f: # Added encoding
        data = json.load(f)
        PRODUCTS = data.get("phones", [])
        if not PRODUCTS:
             logger.warning("No 'phones' list found or list is empty in products.json")
except FileNotFoundError:
    logger.error("CRITICAL: products.json file not found.")
except json.JSONDecodeError as e:
    logger.error(f"CRITICAL: Invalid JSON in products.json - {e}")
except Exception as e:
    logger.error(f"CRITICAL: Unexpected error loading products.json: {e}")


# States for conversation
NAME, PHONE, LOCATION = range(3)

# --- Helper Function ---
def get_product_buttons():
    """Generates inline keyboard buttons for available products."""
    buttons = []
    if not PRODUCTS:
        buttons.append([InlineKeyboardButton("⚠️ No products available", callback_data="no_products")])
    else:
        buttons = [
            # Display name, price, and condition
            [InlineKeyboardButton(f"{p['name']} – {p['price']} ({p.get('condition_label', 'N/A')})", callback_data=str(i))]
            for i, p in enumerate(PRODUCTS)
        ]
    return InlineKeyboardMarkup(buttons)

# --- Command Handlers ---
async def start(update: Update, context: CallbackContext):
    """Handles the /start command."""
    user = update.effective_user
    logger.info("User %s (%s) started the bot.", user.id, user.username or "N/A")
    # Check if already in a conversation and offer to cancel
    if context.user_data.get('state') is not None:
         await update.message.reply_text("You seem to be in the middle of an order. Use /cancel to start over.")
         return

    await update.message.reply_text(
        """👋 Hello! Welcome to UB iPhone Store.
We sell quality refurbished iPhones to University of Botswana students.
Select a phone below to view more details:"""
    )
    if not PRODUCTS:
        await update.message.reply_text("⚠️ Sorry, no phones are listed at the moment. Please check back later.")
    else:
        await update.message.reply_text("Available Phones:", reply_markup=get_product_buttons())

# --- Callback Query Handlers & Conversation Steps ---
async def show_gallery(update: Update, context: CallbackContext):
    """Shows product details and images when a product button is clicked."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    # Store the original message ID if needed for editing later, though we delete it now
    # original_message_id = query.message.message_id

    try:
        phone_index = int(query.data)
        # Add bounds checking for safety
        if not 0 <= phone_index < len(PRODUCTS):
             logger.warning(f"Invalid phone index {phone_index} selected by user {query.from_user.id}")
             # Try editing the original message first
             try:
                 await query.edit_message_text("⚠️ Error: Invalid selection. Please try /start again.")
             except TelegramError as e:
                 logger.error(f"Failed to edit message on invalid index: {e}")
                 # Fallback: send new message if edit fails
                 await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Error: Invalid selection. Please try /start again.")
             return ConversationHandler.END # Exit conversation
        phone = PRODUCTS[phone_index]
    except (ValueError, IndexError) as e:
        logger.error(f"Error processing gallery selection (data: {query.data}): {e}")
        try:
            await query.edit_message_text("⚠️ Error displaying item details. Please try /start again.")
        except TelegramError as edit_e:
             logger.error(f"Failed to edit message on gallery error: {edit_e}")
             await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Error displaying item details. Please try /start again.")
        return ConversationHandler.END

    context.user_data["selected_phone"] = phone_index
    context.user_data['state'] = 'showing_details' # Mark state

    # Build caption using MarkdownV2 (requires careful escaping)
    caption_parts = [
        f"📱 *{escape_markdown(phone.get('name', 'N/A'), version=2)}*",
        f"💰 *Price:* {escape_markdown(phone.get('price', 'N/A'), version=2)}",
        f"✅ *Condition:* {escape_markdown(phone.get('condition_label', 'N/A'), version=2)}",
        f"💾 *Specs:* {escape_markdown(phone.get('specs', 'N/A'), version=2)}",
        f"🔋 *Battery:* {escape_markdown(phone.get('battery_health', 'N/A'), version=2)}",
        f"🧾 *Warranty:* {escape_markdown(phone.get('warranty', 'N/A'), version=2)}",
        f"📝 *Notes:* {escape_markdown(phone.get('notes', 'N/A'), version=2)}",
        f"*Extras:* {escape_markdown(phone.get('extras', 'N/A'), version=2)}"
    ]
    full_caption = "\n".join(caption_parts)

    # Prepare media group
    media_group = []
    image_urls = phone.get("images", [])
    if image_urls:
        # Basic URL validation (optional but helpful)
        valid_urls = [url for url in image_urls if isinstance(url, str) and url.startswith('http')]
        if len(valid_urls) != len(image_urls):
             logger.warning(f"Some invalid image URLs found for phone index {phone_index}")
        media_group = [InputMediaPhoto(media=url) for url in valid_urls]

    # Try deleting the previous message (product list) to avoid clutter
    try:
        await query.delete_message()
        logger.info(f"Deleted original product list message {query.message.message_id}")
    except TelegramError as e:
        # Log if deletion fails but continue
        logger.warning(f"Could not delete message {query.message.message_id}: {e}")

    # Send images if available
    if media_group:
        try:
            await context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group)
            logger.info(f"Sent media group for phone index {phone_index}")
        except TelegramError as e:
            # Log the specific error from Telegram
            logger.error(f"Failed to send media group for phone {phone_index}: {e}")
            # Inform user specifically about image failure
            await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Error sending product images. Displaying details below.")
        except Exception as e:
             # Catch other potential errors during media sending
             logger.error(f"Unexpected error sending media group: {e}")
             await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ An unexpected error occurred sending images.")


    # Send the caption text and buttons in a NEW message
    # This new message will have its own context for callbacks
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes, proceed with this phone", callback_data="confirm")],
        [InlineKeyboardButton("Back to list", callback_data="back")]
    ])

    try:
        # Send the new message with details and buttons
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=full_caption + "\n\n*Would you like to proceed with this phone\\?*", # Escape '?' for MarkdownV2
            reply_markup=keyboard,
            parse_mode='MarkdownV2'
        )
        logger.info(f"Sent product details message for phone index {phone_index}")
    except TelegramError as e:
        logger.error(f"Failed to send product details message for phone {phone_index} (MarkdownV2): {e}")
        # Attempt to send a plain text fallback if Markdown fails
        try:
             await context.bot.send_message(
                 chat_id=query.message.chat_id,
                 text=f"Details for {phone.get('name', 'N/A')}.\nPrice: {phone.get('price', 'N/A')}.\nProceed?", # Simple text
                 reply_markup=keyboard
             )
        except TelegramError as fallback_e:
             logger.error(f"Failed to send fallback message: {fallback_e}")

    # Since we sent a new message, the ConversationHandler needs to correctly
    # associate the button presses from this new message.
    # Returning None keeps the handler active, waiting for fallbacks.
    return None


async def confirm_handler(update: Update, context: CallbackContext):
    """Handles 'confirm' or 'back' button presses. Edits are unreliable, so delete and send new."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    # --- Delete the message with the buttons ---
    try:
        await query.delete_message()
        logger.info(f"Deleted details/button message {query.message.message_id}")
    except TelegramError as e:
        logger.warning(f"Could not delete details/button message {query.message.message_id}: {e}")
        # Try editing to remove buttons as a fallback if delete fails
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except TelegramError as edit_e:
            logger.warning(f"Could not remove buttons via edit either: {edit_e}")

    # --- Perform action based on button ---
    if query.data == "confirm":
        # Send a new message asking for the name
        await context.bot.send_message(chat_id=chat_id, text="📝 Great! Please provide your full name:")
        context.user_data['state'] = NAME # Update state tracker
        return NAME # Transition to NAME state

    elif query.data == "back":
        # Send a new message showing the product list
        await context.bot.send_message(
            chat_id=chat_id,
            text="Available Phones:",
            reply_markup=get_product_buttons()
        )
        context.user_data.clear() # Clear data when going back to start
        # End the conversation here, user needs to click a product again
        return ConversationHandler.END

    elif query.data == "no_products":
         # Send a new message if "no products" was clicked
         await context.bot.send_message(chat_id=chat_id, text="Currently no products listed. Please check back later.")
         context.user_data.clear()
         return ConversationHandler.END


# --- State Handlers ---
async def collect_name(update: Update, context: CallbackContext):
    """Collects the user's name."""
    name = update.message.text.strip()
    if len(name) < 2: # Basic validation
        await update.message.reply_text("Please enter a valid full name.")
        return NAME # Stay in the same state
    context.user_data["name"] = name
    context.user_data['state'] = PHONE # Update state tracker
    await update.message.reply_text("📞 Got it. Now, please provide your phone number.")
    return PHONE # Transition to PHONE state

async def collect_phone(update: Update, context: CallbackContext):
    """Collects the user's phone number."""
    phone_number = update.message.text.strip()
    # Basic validation (e.g., check if it contains digits, length)
    # You might want more robust validation depending on expected formats
    if not any(char.isdigit() for char in phone_number) or len(phone_number) < 7:
        await update.message.reply_text("Please enter a valid phone number.")
        return PHONE # Stay in the same state
    context.user_data["phone"] = phone_number
    context.user_data['state'] = LOCATION # Update state tracker
    await update.message.reply_text("🏫 Almost there! Please provide your Campus Location or preferred Exchange Point:\n(e.g., Block C Room 104, Library Entrance)")
    return LOCATION # Transition to LOCATION state

async def collect_location(update: Update, context: CallbackContext):
    """Collects the delivery location and finalizes the order request."""
    location = update.message.text.strip()
    if len(location) < 5: # Basic validation
        await update.message.reply_text("Please enter a valid location.")
        return LOCATION # Stay in the same state

    context.user_data["location"] = location

    # --- Final Summary and Notification ---
    try:
        selected_index = context.user_data.get("selected_phone")
        # Safety check for index
        if selected_index is None or not 0 <= selected_index < len(PRODUCTS):
             logger.error(f"Invalid or missing selected_phone index ({selected_index}) in user_data for user {update.effective_user.id}")
             await update.message.reply_text("❌ An error occurred retrieving your selection. Please try /start again.")
             context.user_data.clear() # Clear data on error
             return ConversationHandler.END

        phone = PRODUCTS[selected_index]
        user_name = context.user_data.get('name', 'N/A')
        user_phone = context.user_data.get('phone', 'N/A')

        # Summary for user (escape markdown characters)
        # Use double backslashes \\ to escape for Python f-string AND MarkdownV2
        summary = (
            f"✅ Thank you, {escape_markdown(user_name, version=2)}\\!\n\n"
            f"Your order request has been received\\. We'll contact you soon via Telegram or phone \\({escape_markdown(user_phone, version=2)}\\) to confirm pickup/delivery details\\.\n\n"
            f"*Your Request Summary:*\n"
            f"📱 Phone: {escape_markdown(phone.get('name', 'N/A'), version=2)}\n"
            f"💰 Price: {escape_markdown(phone.get('price', 'N/A'), version=2)}\n"
            f"📍 Delivery/Pickup: {escape_markdown(location, version=2)}"
        )
        await update.message.reply_text(summary, parse_mode='MarkdownV2')
        logger.info(f"Order summary sent to user {update.effective_user.id}")

        # Send notification to Admin
        if ADMIN_CHAT_ID:
            # Escape content for admin message too
            admin_summary = (
                f"🚨 *NEW ORDER REQUEST* 🚨\n\n"
                f"👤 *Name:* {escape_markdown(user_name, version=2)}\n"
                f"📞 *Phone:* {escape_markdown(user_phone, version=2)}\n"
                f"📍 *Location:* {escape_markdown(location, version=2)}\n"
                f"📱 *Selected:* {escape_markdown(phone.get('name', 'N/A'), version=2)} – {escape_markdown(phone.get('price', 'N/A'), version=2)}\n"
                f"🆔 *User ID:* `{update.effective_user.id}`" # User ID doesn't need escaping
            )
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_summary, parse_mode='MarkdownV2')
                logger.info(f"Order notification sent to admin {ADMIN_CHAT_ID}")
            except TelegramError as admin_err:
                logger.error(f"Failed to send message to ADMIN_CHAT_ID {ADMIN_CHAT_ID}: {admin_err}")
            except Exception as e: # Catch other potential errors
                 logger.error(f"Unexpected error sending admin notification: {e}")
        else:
            logger.warning("ADMIN_CHAT_ID not set. Cannot send order notification.")

    except Exception as e:
        logger.error(f"Error finalizing order or sending notifications: {e}")
        await update.message.reply_text("❌ An error occurred while processing your request. Please try /start again.")

    finally:
        # Clear user data for this conversation to prevent issues with next order
        context.user_data.clear()
        logger.info(f"User data cleared for user {update.effective_user.id}, conversation ended.")
        return ConversationHandler.END # End the conversation


# --- Fallback Handlers ---
async def cancel(update: Update, context: CallbackContext):
    """Cancels the current conversation."""
    user = update.effective_user
    logger.info("User %s (%s) cancelled the conversation.", user.id, user.username or "N/A")
    await update.message.reply_text("❌ Order request cancelled. You can start again anytime with /start.")
    # Clear user data upon cancellation
    context.user_data.clear()
    return ConversationHandler.END

# --- Error Handler ---
async def error_handler(update: object, context: CallbackContext):
    """Log Errors caused by Updates."""
    # Log the error before handling it
    logger.error('Update "%s" caused error "%s"', update, context.error, exc_info=context.error)

    # Optionally, inform the user that an error occurred.
    # Be careful not to spam users if the error happens frequently.
    # if isinstance(update, Update) and update.effective_chat:
    #     try:
    #         await context.bot.send_message(
    #             chat_id=update.effective_chat.id,
    #             text="Apologies, a technical error occurred. Please try again later or use /cancel."
    #         )
    #     except Exception as send_err:
    #         logger.error(f"Failed to send error notification to user: {send_err}")


# --- Keep Alive Web Server ---
app = Flask('')

@app.route('/')
def home():
    """Basic route for the keep-alive server."""
    return "Bot is alive!"

def run_server():
    """Runs the Flask server."""
    # Use the PORT environment variable provided by many platforms
    port = int(os.environ.get('PORT', 8080))
    # Run on 0.0.0.0 to be accessible externally
    # Disable Flask's default logging if PTB logging is sufficient
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING) # Only show warnings/errors from Flask
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Starts the Flask server in a separate thread."""
    server = Thread(target=run_server)
    # Daemon threads exit when the main program exits
    server.daemon = True
    server.start()
    logger.info("Keep-alive server started.")

# --- Main Bot Execution ---
if __name__ == "__main__":
    # --- Check Prerequisites ---
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in environment variables/Secrets! Exiting.")
        import sys
        sys.exit(1) # Exit if no token
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is not set in environment variables/Secrets. Admin notifications disabled.")

    if not PRODUCTS:
         logger.warning("Product list is empty. Check products.json and potential loading errors.")

    # Start the keep-alive thread
    keep_alive()

    # --- Build Application ---
    # Consider adding persistence if you want conversations to survive restarts
    # from telegram.ext import PicklePersistence
    # persistence = PicklePersistence(filepath="bot_conversation_persistence")
    # application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    # Build the application
    application = Application.builder().token(BOT_TOKEN).build()


    # --- Conversation Handler Setup ---
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_gallery, pattern=r'^\d+$')], # Product index
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_location)]
        },
        fallbacks=[
            CallbackQueryHandler(confirm_handler, pattern="^(confirm|back)$"), # Confirm/Back buttons
            CallbackQueryHandler(confirm_handler, pattern="^no_products$"), # "No products" button
            CommandHandler("cancel", cancel) # /cancel command
        ],
        # conversation_timeout=300 # Optional: Add timeout in seconds (e.g., 5 minutes)
        # Name the conversation for persistence if used
        # name="order_conversation",
        # persistent=True # If using persistence
    )

    # --- Add Handlers to Application ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler) # Add the conversation handler

    # Add the error handler LAST
    application.add_error_handler(error_handler)

    # --- Start the Bot ---
    logger.info("Starting bot polling...")
    # run_polling() will run indefinitely until interrupted (like Ctrl+C)
    # It handles the asyncio loop internally.
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Specify allowed updates
    logger.info("Bot polling stopped.") # This line is reached when polling stops

