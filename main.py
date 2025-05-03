import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
                        Updater,
                        CommandHandler,
                        CallbackQueryHandler,
                        ConversationHandler,
                        MessageHandler,
                        Filters,
                        CallbackContext,
                    )
                    # --- Keep Alive Imports ---
from flask import Flask
from threading import Thread
                    # --------------------------

                    # --- Configuration ---
                    # IMPORTANT: Set these in Replit Secrets (Padlock icon)! Do not rely on defaults.
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") # Replace default with "" or None if preferred
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "YOUR_ADMIN_CHAT_ID_HERE") # Replace default with "" or None if preferred

                    # Set up logging
logging.basicConfig(
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO
                    )
logger = logging.getLogger(__name__) # <--- Corrected Indentation

                    # Load products safely
PRODUCTS = [] # Initialize as empty list
try:                                          # <-- Base Level Indentation
                        with open("products.json", "r") as f:     # <-- Indented under try
                            data = json.load(f)                   # <-- Indented under with
                            PRODUCTS = data.get("phones", [])     # <-- Indented under with
                            if not PRODUCTS:                      # <-- Indented under with
                                # Log a warning but don't exit, maybe admin needs to add products
                                logger.warning("No 'phones' list found or list is empty in products.json")
                                # raise ValueError("No phones found in products.json") # Optional: uncomment to make it fatal
                    except FileNotFoundError:                    # <-- Base Level Indentation (Aligned with try)
                        logger.error("CRITICAL: products.json file not found. Bot may not function correctly.")
                        # Optional: uncomment below to stop the bot if products are essential
                        # raise SystemExit("CRITICAL: products.json file not found.")
                    except json.JSONDecodeError:                # <-- Base Level Indentation (Aligned with try)
                        logger.error("CRITICAL: Invalid JSON in products.json. Please validate the file.")
                        # Optional: uncomment below to stop the bot
                        # raise SystemExit("CRITICAL: Invalid JSON in products.json")
                    except Exception as e:                      # Catch any other unexpected errors during loading
                        logger.error(f"CRITICAL: Unexpected error loading products.json: {e}")
                        # Optional: uncomment below to stop the bot
                        # raise SystemExit(f"CRITICAL: Unexpected error loading products.json: {e}")


                    # States for conversation
                    NAME, PHONE, LOCATION = range(3)

                    # --- Helper Function ---
                    def get_product_buttons():
                        buttons = []
                        if not PRODUCTS:
                             buttons.append([InlineKeyboardButton("⚠️ No products available", callback_data="no_products")])
                        else:
                            buttons = [
                                [InlineKeyboardButton(f"{p['name']} – {p['price']} ({p['condition_label']})", callback_data=str(i))]
                                for i, p in enumerate(PRODUCTS)
                            ]
                        return InlineKeyboardMarkup(buttons)

                    # --- Command Handlers ---
                    def start(update: Update, context: CallbackContext):
                        user_id = update.effective_user.id
                        logger.info("User %s started the bot.", user_id)
                        update.message.reply_text(
                            "👋 Hello! Welcome to UB iPhone Store.\n"
                            "We sell quality refurbished iPhones to University of Botswana students.\n"
                            "Select a phone below to view more details:"
                        )
                        # Check if PRODUCTS loaded correctly before sending buttons
                        if not PRODUCTS:
                             update.message.reply_text("⚠️ Sorry, no phones are listed at the moment. Please check back later.")
                        else:
                            update.message.reply_text("Available Phones:", reply_markup=get_product_buttons())

                    # --- Callback Query Handlers & Conversation Steps ---
                    def show_gallery(update: Update, context: CallbackContext):
                        query = update.callback_query
                        query.answer()
                        try:
                            phone_index = int(query.data)
                            context.user_data["selected_phone"] = phone_index

                            # Ensure PRODUCTS list is not empty and index is valid
                            if not PRODUCTS or phone_index < 0 or phone_index >= len(PRODUCTS):
                                 logger.warning(f"Invalid phone index {phone_index} selected by user {query.from_user.id}")
                                 query.edit_message_text("⚠️ Error: Invalid selection. Please try starting again with /start.")
                                 return ConversationHandler.END # Exit conversation if product selection is invalid

                            phone = PRODUCTS[phone_index]

                            # Build caption first
                            caption = (
                                f"📱 *{phone['name']}*\n\n"
                                f"💰 *Price:* {phone['price']}\n"
                                f"✅ *Condition:* {phone.get('condition_label', 'N/A')}\n"
                                f"💾 *Specs:* {phone.get('specs', 'N/A')}\n"
                                f"🔋 *Battery:* {phone.get('battery_health', 'N/A')}\n" # Use .get() for optional fields
                                f"🧾 *Warranty:* {phone.get('warranty', 'N/A')}\n\n" # Use .get() for optional fields
                                f"📝 *Notes:* {phone.get('notes', 'N/A')}\n"
                                f"*Extras:* {phone.get('extras', 'N/A')}"
                            )

                            # Send media group (gallery of images) if images exist
                            media_group = []
                            if phone.get("images"): # Check if the images key exists and is not empty
                                 media_group = [InputMediaPhoto(media=url) for url in phone["images"]]

                            if media_group:
                                # Delete the original product list message before sending gallery
                                # This prevents clutter and potential errors if trying to edit later
                                try:
                                    query.delete_message()
                                except Exception as del_err:
                                    logger.warning(f"Could not delete original message: {del_err}")

                                context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group)
                                # Send caption in a new message after the gallery
                                keyboard = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("Yes, proceed with this phone", callback_data="confirm")],
                                    [InlineKeyboardButton("Back to list", callback_data="back")]
                                ])
                                context.bot.send_message(
                                    chat_id=query.message.chat_id,
                                    text=caption + "\n\n*Would you like to proceed with this phone?*",
                                    reply_markup=keyboard,
                                    parse_mode='Markdown'
                                )
                                # Since we sent a new message, the conversation entry point needs adjustment or
                                # we rely on the confirm_handler to manage state from the new message's callback
                            else:
                                # If no images, edit the original message with details and buttons
                                keyboard = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("Yes, proceed with this phone", callback_data="confirm")],
                                    [InlineKeyboardButton("Back to list", callback_data="back")]
                                ])
                                query.edit_message_text(
                                    caption + "\n\n*Would you like to proceed with this phone?*",
                                    reply_markup=keyboard,
                                    parse_mode='Markdown'
                                )
                            # This function is the entry point, but doesn't return a state itself.
                            # The state transition happens in confirm_handler based on the button pressed.
                            # Return None or simply don't return to stay 'outside' the conversation states until 'confirm' is hit.
                            return None # Or just omit return

                        except (ValueError, IndexError) as e:
                             logger.error(f"Error processing gallery selection (data: {query.data}): {e}")
                             query.edit_message_text("⚠️ Error displaying item details. Please try starting again with /start.")
                             return ConversationHandler.END
                        except Exception as e:
                             logger.error(f"Unexpected error in show_gallery: {e}")
                             try:
                                query.edit_message_text("⚠️ An unexpected error occurred. Please try again later or contact support.")
                             except Exception as edit_err:
                                logger.error(f"Failed to send error message back to user: {edit_err}")
                             return ConversationHandler.END

                    def confirm_handler(update: Update, context: CallbackContext):
                        query = update.callback_query
                        query.answer()
                        try:
                            if query.data == "confirm":
                                # Ask for name by editing the message with the details/buttons
                                query.edit_message_text("📝 Great! Please provide your full name:", reply_markup=None) # Remove buttons
                                return NAME # Transition to NAME state
                            elif query.data == "back":
                                # Edit the message back to the product list
                                query.edit_message_text("Available Phones:", reply_markup=get_product_buttons())
                                # We are going 'back' but not really ending the conversation's logical flow yet,
                                # Returning END here means the user needs to click a product again to trigger show_gallery
                                return ConversationHandler.END
                            elif query.data == "no_products":
                                 query.edit_message_text("Currently no products listed. Please check back later.")
                                 return ConversationHandler.END

                        except Exception as e:
                            logger.error(f"Error in confirm_handler: {e}")
                            # Attempt to edit message, otherwise log failure
                            try:
                                query.edit_message_text("An error occurred. Please try starting again with /start.", reply_markup=None)
                            except Exception as edit_err:
                                 logger.error(f"Failed to send error message back to user during confirm_handler: {edit_err}")
                            return ConversationHandler.END

                    # --- State Handlers ---
                    def collect_name(update: Update, context: CallbackContext):
                        try:
                            user_input = update.message.text
                            if not user_input or len(user_input) < 2: # Basic validation
                                 update.message.reply_text("Please enter a valid full name.")
                                 return NAME # Stay in the same state
                            context.user_data["name"] = user_input
                            update.message.reply_text("📞 Got it. Now, please provide your phone number:")
                            return PHONE # Transition to PHONE state
                        except Exception as e:
                            logger.error(f"Error collecting name: {e}")
                            update.message.reply_text("❌ Something went wrong. Please try /start again.")
                            return ConversationHandler.END

                    def collect_phone(update: Update, context: CallbackContext):
                        try:
                            user_input = update.message.text
                            # Basic validation (e.g., check if it contains digits, length)
                            if not user_input or not any(char.isdigit() for char in user_input) or len(user_input) < 7:
                                 update.message.reply_text("Please enter a valid phone number.")
                                 return PHONE # Stay in the same state
                            context.user_data["phone"] = user_input
                            update.message.reply_text("🏫 Almost there! Please provide your Campus Location or preferred Exchange Point:\n(e.g., Block C Room 104, Library Entrance, UB Circle)")
                            return LOCATION # Transition to LOCATION state
                        except Exception as e:
                            logger.error(f"Error collecting phone: {e}")
                            update.message.reply_text("❌ Something went wrong. Please try /start again.")
                            return ConversationHandler.END

                    def collect_location(update: Update, context: CallbackContext):
                        try:
                            user_data = context.user_data
                            user_input = update.message.text
                            if not user_input or len(user_input) < 5: # Basic validation
                                update.message.reply_text("Please enter a valid location or exchange point.")
                                return LOCATION # Stay in the same state

                            user_data["location"] = user_input

                            # Get selected phone safely
                            selected_index = user_data.get("selected_phone")
                            if selected_index is None or selected_index < 0 or selected_index >= len(PRODUCTS):
                                 logger.error(f"Invalid or missing selected_phone index ({selected_index}) in user_data for user {update.effective_user.id}")
                                 update.message.reply_text("❌ An error occurred retrieving your selection. Please try /start again.")
                                 return ConversationHandler.END

                            phone = PRODUCTS[selected_index]

                            # Summary for user
                            summary = (
                                f"✅ Thank you, {user_data.get('name', 'Customer')}!\n\n"
                                f"Your order request has been received. We'll contact you soon via Telegram or phone ({user_data.get('phone', 'N/A')}) to confirm pickup/delivery details.\n\n"
                                f"*Your Request Summary:*\n"
                                f"📱 Phone: {phone['name']}\n"
                                f"💰 Price: {phone['price']}\n"
                                f"📍 Delivery/Pickup: {user_data['location']}"
                            )
                            update.message.reply_text(summary, parse_mode='Markdown')

                            # Send to admin (Check if ADMIN_CHAT_ID is set)
                            if ADMIN_CHAT_ID and ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID_HERE":
                                admin_summary = (
                                    f"🚨 *NEW ORDER REQUEST* 🚨\n\n"
                                    f"👤 *Name:* {user_data.get('name', 'N/A')}\n"
                                    f"📞 *Phone:* {user_data.get('phone', 'N/A')}\n"
                                    f"📍 *Location/Exchange:* {user_data.get('location', 'N/A')}\n"
                                    f"📱 *Selected Phone:* {phone['name']} ({phone['price']})\n"
                                    f"🆔 *User ID:* {update.effective_user.id}"
                                )
                                try:
                                    context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_summary, parse_mode='Markdown')
                                except Exception as admin_err:
                                    logger.error(f"Failed to send message to ADMIN_CHAT_ID {ADMIN_CHAT_ID}: {admin_err}")
                            else:
                                logger.warning("ADMIN_CHAT_ID not set in Secrets. Cannot send order notification.")

                            # Clear user data for this conversation if desired
                            # context.user_data.clear()

                            return ConversationHandler.END # End the conversation

                        except Exception as e:
                            logger.error(f"Error collecting location or finalizing order: {e}")
                            update.message.reply_text("❌ Something went wrong processing your request. Please try /start again.")
                            return ConversationHandler.END

                    # --- Fallback Handlers ---
                    def cancel(update: Update, context: CallbackContext):
                        user_id = update.effective_user.id
                        logger.info("User %s cancelled the conversation.", user_id)
                        update.message.reply_text("❌ Order request cancelled. You can start again anytime with /start.")
                        # Clear user data if needed
                        # context.user_data.clear()
                        return ConversationHandler.END

                    def error_handler(update: object, context: CallbackContext):
                        """Log Errors caused by Updates."""
                        logger.error('Update "%s" caused error "%s"', update, context.error, exc_info=context.error)
                        # Optionally notify user or admin about unexpected errors
                        # if isinstance(update, Update) and update.effective_chat:
                        #     try:
                        #         context.bot.send_message(chat_id=update.effective_chat.id, text="Apologies, a technical error occurred. Please try again later.")
                        #     except Exception as send_err:
                        #          logger.error(f"Failed to send error message to user: {send_err}")


                    # --- Keep Alive Web Server ---
                    app = Flask('')

                    @app.route('/')
                    def home():
                        return "Bot is alive!"

                    def run():
                        # Make sure to run on 0.0.0.0 and port specified by Replit or a common one like 8080
                        port = int(os.environ.get('PORT', 8080))
                        app.run(host='0.0.0.0', port=port)

                    def keep_alive():
                        t = Thread(target=run)
                        t.start()

                    # --- Main Bot Execution ---
                    def main():
                        # --- Check Prerequisites ---
                        if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                            logger.critical("BOT_TOKEN is not set in environment variables/Secrets! Exiting.")
                            return # Exit if no token
                        if not ADMIN_CHAT_ID or ADMIN_CHAT_ID == "YOUR_ADMIN_CHAT_ID_HERE":
                            logger.warning("ADMIN_CHAT_ID is not set in environment variables/Secrets. Admin notifications disabled.")
                        if not PRODUCTS:
                             logger.warning("Product list is empty. Check products.json and potential loading errors.")

                        keep_alive()  # Start the Flask keep-alive thread

                        updater = Updater(BOT_TOKEN, use_context=True)
                        dp = updater.dispatcher

                        # --- Conversation Handler Setup ---
                        conv_handler = ConversationHandler(
                            entry_points=[
                                 # Entry point is clicking a product button after /start
                                 # Pattern matches the index sent as callback data
                                 CallbackQueryHandler(show_gallery, pattern=r"^\d+$")
                            ],
                            states={
                                # States triggered by user text messages after prompts
                                NAME: [MessageHandler(Filters.text & ~Filters.command, collect_name)],
                                PHONE: [MessageHandler(Filters.text & ~Filters.command, collect_phone)],
                                LOCATION: [MessageHandler(Filters.text & ~Filters.command, collect_location)],
                            },
                            fallbacks=[
                                # Handles "confirm" and "back" buttons from the product detail message
                                CallbackQueryHandler(confirm_handler, pattern="^confirm$|^back$"),
                                # Handles clicking "No products available" button
                                CallbackQueryHandler(confirm_handler, pattern="^no_products$"),
                                # Handles /cancel command at any point in the conversation
                                CommandHandler("cancel", cancel),
                                # You might add a fallback for unexpected text messages during conversation states
                                # MessageHandler(Filters.text & ~Filters.command, unexpected_input_handler)
                            ],
                            # Optional: configure conversation timeouts, persistence etc.
                        )

                        # --- Add Handlers to Dispatcher ---
                        dp.add_handler(CommandHandler("start", start))
                        dp.add_handler(conv_handler) # Add the conversation handler

                        # Add the error handler LAST
                        dp.add_error_handler(error_handler)

                        # --- Start the Bot ---
                        logger.info("Bot is starting polling...")
                        updater.start_polling()
                        logger.info("Bot has started successfully.")
                        updater.idle() # Keep the script running until interrupted (e.g., Ctrl+C)
                        logger.info("Bot is stopping.")


                    if __name__ == "__main__":
                        main()