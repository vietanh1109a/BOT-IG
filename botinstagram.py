import requests
import logging
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import time
import asyncio
import re
from typing import List, Dict, Any, Union, Optional

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token bot
TOKEN = "7165323948:AAGe59mWIO0IhabXkeXPUyBikXmYcMeaQj4"

# URL API Instagram
INSTAGRAM_API_URL = "https://subhatde.id.vn/instagram/post?q="
INSTAGRAM_INFO_API_URL = "https://subhatde.id.vn/instagram/info?q="
INSTAGRAM_POST_URL_API = "https://subhatde.id.vn/instagram/url?q="

# Timeout cho các yêu cầu API (giây)
API_TIMEOUT = 30

# Kích thước tối đa cho một media group trong Telegram (10)
MAX_MEDIA_GROUP_SIZE = 10

# Thời gian đợi giữa các yêu cầu để tránh rate limits
RATE_LIMIT_DELAY = 0.5

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn khi lệnh /start được sử dụng."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! Tôi là bot Instagram .\n"
        f"Tôi có thể lấy bài đăng và thông tin người dùng Instagram.\n\n"
        f"Sử dụng /getpost [username] - Lấy bài đăng Instagram của người dùng.\n"
        f"Sử dụng /getinfo [username] - Lấy thông tin chi tiết về tài khoản Instagram."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gửi tin nhắn khi lệnh /help được sử dụng."""
    await update.message.reply_text(
        "Các lệnh:\n"
        "/start - Khởi động bot\n"
        "/help - Hiển thị hướng dẫn này\n"
        "/getpost [username] - Lấy bài đăng Instagram của người dùng\n"
        "/getinfo [username] - Lấy thông tin chi tiết về tài khoản Instagram\n\n"
    )

def format_number(num: Union[int, str, None]) -> str:
    """Định dạng số để dễ đọc."""
    if num is None:
        return "N/A"
    
    if isinstance(num, str):
        try:
            num = int(num)
        except ValueError:
            return num
    
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(num)

async def send_media_group_safely(update: Update, media_items: List[Dict[str, Any]], caption: str) -> bool:
    """Gửi nhóm media với xử lý lỗi và không đặt caption cho từng item."""
    if not media_items or len(media_items) == 0:
        return False
    
    try:
        # Gửi thông tin caption trước
        caption_message = await update.message.reply_text(caption)
        
        # Chuẩn bị media_group
        media_group = []
        for item in media_items:
            if isinstance(item, dict):
                media_type = item.get("type", "").lower()
                media_url = item.get("url", "")
                
                if not media_url:
                    continue
                
                try:
                    if media_type in ["image", "carousel"]:
                        media_group.append(InputMediaPhoto(media=media_url))
                    elif media_type == "video":
                        media_group.append(InputMediaVideo(media=media_url))
                except Exception as e:
                    logger.error(f"Lỗi khi thêm media vào group: {e}")
            elif isinstance(item, str):  # Nếu chỉ là URL
                try:
                    if item.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        media_group.append(InputMediaPhoto(media=item))
                    elif item.lower().endswith(('.mp4', '.mov', '.avi')):
                        media_group.append(InputMediaVideo(media=item))
                except Exception as e:
                    logger.error(f"Lỗi khi thêm URL vào media group: {e}")
        
        if not media_group:
            await update.message.reply_text(f"{caption}\n\n(Không thể tải media)")
            return False
        
        # Chia thành nhóm media nhỏ hơn
        success = True
        for i in range(0, len(media_group), MAX_MEDIA_GROUP_SIZE):
            chunk = media_group[i:i + MAX_MEDIA_GROUP_SIZE]
            if not chunk:
                continue
                
            try:
                await update.message.reply_media_group(media=chunk)
                await asyncio.sleep(RATE_LIMIT_DELAY)  # Tránh rate limit
            except Exception as e:
                logger.error(f"Lỗi khi gửi media group: {e}")
                # Nếu không gửi được nhóm, thử gửi từng cái
                chunk_success = await send_media_individually(update, chunk)
                success = success and chunk_success
        
        return success
    except Exception as e:
        logger.error(f"Lỗi tổng thể khi gửi media group: {e}")
        # Fallback: Gửi từng ảnh nếu không gửi được nhóm
        await send_media_individually(update, media_items, caption)
        return False

async def send_media_individually(update: Update, media_items: List[Any], caption: Optional[str] = None) -> bool:
    """Gửi từng media riêng lẻ khi không thể gửi nhóm."""
    success = True
    
    # Gửi caption một lần nếu được cung cấp và chưa được gửi
    if caption and not isinstance(media_items[0], (InputMediaPhoto, InputMediaVideo)):
        await update.message.reply_text(caption)
        caption = None  # Đã gửi caption, không gửi lại
    
    for item in media_items:
        try:
            media_url = None
            media_type = None
            
            if isinstance(item, InputMediaPhoto):
                media_url = item.media
                media_type = "image"
            elif isinstance(item, InputMediaVideo):
                media_url = item.media
                media_type = "video"
            elif isinstance(item, dict):
                media_type = item.get("type", "").lower()
                media_url = item.get("url", "")
            elif isinstance(item, str):
                media_url = item
                if item.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    media_type = "image"
                elif item.lower().endswith(('.mp4', '.mov', '.avi')):
                    media_type = "video"
            
            if media_url and media_type:
                try:
                    if media_type in ["image", "carousel"]:
                        await update.message.reply_photo(
                            photo=media_url,
                            caption=caption if caption else None
                        )
                    elif media_type == "video":
                        await update.message.reply_video(
                            video=media_url,
                            caption=caption if caption else None
                        )
                    
                    # Đã gửi caption với media đầu tiên, không gửi lại với các media khác
                    caption = None
                    
                    # Độ trễ nhỏ để tránh rate limit
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                except Exception as e:
                    logger.error(f"Lỗi khi gửi media riêng lẻ: {e}")
                    success = False
        except Exception as e:
            logger.error(f"Lỗi khi xử lý media riêng lẻ: {e}")
            success = False
    
    return success

async def get_instagram_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lấy thông tin chi tiết về tài khoản Instagram."""
    if not context.args:
        await update.message.reply_text("Vui lòng cung cấp username Instagram. Ví dụ: /getinfo username")
        return
    
    user_id = context.args[0].strip('@')  # Loại bỏ @ nếu người dùng nhập vào
    status_message = await update.message.reply_text(f"Đang lấy thông tin Instagram của {user_id}...")
    
    try:
        # Thêm timeout để tránh treo
        response = requests.get(f"{INSTAGRAM_INFO_API_URL}{user_id}", timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                if isinstance(data, dict):
                    await process_user_info_dict(update, data, user_id)
                elif isinstance(data, list) and len(data) > 0:
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        await process_user_info_dict(update, first_item, user_id)
                    else:
                        await update.message.reply_text("Không thể phân tích thông tin từ dữ liệu danh sách")
                else:
                    await update.message.reply_text(
                        f"Không tìm thấy thông tin hoặc dữ liệu không đúng định dạng.\n"
                        f"Kiểu dữ liệu nhận được: {type(data).__name__}"
                    )
            except ValueError as json_error:
                logger.error(f"Lỗi khi phân tích JSON: {json_error}")
                await update.message.reply_text(f"Lỗi khi phân tích dữ liệu: {str(json_error)}")
        else:
            error_msg = f"Lỗi: API trả về mã trạng thái {response.status_code}"
            
            # Thử đọc thông báo lỗi từ phản hồi
            try:
                error_data = response.json()
                if isinstance(error_data, dict) and ("error" in error_data or "message" in error_data):
                    error_detail = error_data.get("error", error_data.get("message", ""))
                    error_msg += f"\nChi tiết: {error_detail}"
            except:
                # Nếu không phải JSON, lấy một phần text
                if response.text:
                    error_msg += f"\nPhản hồi: {response.text[:100]}..."
            
            await update.message.reply_text(error_msg)
    
    except requests.exceptions.Timeout:
        await update.message.reply_text(f"Yêu cầu API bị timeout. Vui lòng thử lại sau.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kết nối API: {e}")
        await update.message.reply_text(f"Lỗi kết nối đến API: {str(e)}")
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin Instagram: {e}")
        await update.message.reply_text(f"Xin lỗi, đã xảy ra lỗi: {str(e)}")
    finally:
        # Xóa thông báo trạng thái
        try:
            await status_message.delete()
        except:
            pass

async def process_user_info_dict(update: Update, data: Dict[str, Any], user_id: str) -> None:
    """Xử lý và hiển thị thông tin người dùng từ dữ liệu dạng dictionary."""
    # Kiểm tra xem có thông báo lỗi trong JSON không
    if "error" in data or "message" in data and not data.get("username"):
        error_msg = data.get("error", data.get("message", "Unknown error"))
        await update.message.reply_text(f"API trả về lỗi: {error_msg}")
        return
    
    # Lấy các thông tin cơ bản với giá trị mặc định an toàn hơn
    username = data.get("username", user_id)
    
    # Kiểm tra các trường tên thay thế
    full_name = data.get("full_name", "")
    if not full_name:
        full_name = data.get("fullName", data.get("name", data.get("fullname", "N/A")))
    
    # Kiểm tra nhiều trường có thể chứa tiểu sử
    biography = data.get("biography", "")
    if not biography:
        biography = data.get("bio", data.get("description", "N/A"))
    
    # Kiểm tra nhiều trường có thể chứa số lượng follower
    followers = data.get("followers", 0)
    if followers == 0:
        followers = data.get("follower_count", 
                   data.get("edge_followed_by", {}).get("count", 
                   data.get("followed_by", {}).get("count", 0)))
    
    # Kiểm tra nhiều trường có thể chứa số lượng following
    following = data.get("following", 0)
    if following == 0:
        following = data.get("following_count", 
                   data.get("edge_follow", {}).get("count", 
                   data.get("follows", {}).get("count", 0)))
    
    # Kiểm tra nhiều trường có thể chứa số lượng bài viết
    posts_count = data.get("posts", 0)
    if posts_count == 0:
        posts_count = data.get("post_count", data.get("media_count", 
                    data.get("edge_owner_to_timeline_media", {}).get("count", 0)))
    
    # Các thuộc tính khác
    is_private = data.get("is_private", data.get("private", False))
    is_verified = data.get("is_verified", data.get("verified", False))
    
    # Tìm URL ảnh đại diện trong nhiều trường có thể chứa
    profile_pic_url = data.get("profile_pic_url", "")
    if not profile_pic_url:
        profile_pic_url = data.get("profilePicUrl", 
                         data.get("profile_picture", 
                         data.get("profile_pic_url_hd", 
                         data.get("hd_profile_pic_url_info", {}).get("url", ""))))
    
    # Tạo text thông tin
    info_text = (
        f"📊 THÔNG TIN INSTAGRAM\n\n"
        f"👤 Username: @{username}\n"
        f"📝 Tên: {full_name}\n"
        f"✅ Tài khoản xác thực: {'Có' if is_verified else 'Không'}\n"
        f"🔒 Tài khoản riêng tư: {'Có' if is_private else 'Không'}\n"
        f"👥 Người theo dõi: {format_number(followers)}\n"
        f"👣 Đang theo dõi: {format_number(following)}\n"
        f"📷 Số bài viết: {format_number(posts_count)}\n"
    )
    
    # Thêm tiểu sử nếu có
    if biography and biography != "N/A":
        info_text += f"\n📜 Tiểu sử:\n{biography}\n"
    
    # Gửi tin nhắn với ảnh đại diện nếu có
    if profile_pic_url:
        try:
            await update.message.reply_photo(photo=profile_pic_url, caption=info_text)
        except Exception as pic_error:
            logger.error(f"Lỗi khi gửi ảnh đại diện: {pic_error}")
            await update.message.reply_text(info_text + "\n\n(Không thể hiển thị ảnh đại diện)")
    else:
        await update.message.reply_text(info_text)

async def get_instagram_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lấy bài đăng Instagram cho username và gửi dưới dạng ảnh/video."""
    if not context.args:
        await update.message.reply_text("Vui lòng cung cấp username Instagram. Ví dụ: /getpost username")
        return
    
    user_id = context.args[0].strip('@')  # Loại bỏ @ nếu người dùng nhập vào
    status_message = await update.message.reply_text(f"Đang tìm bài đăng Instagram cho user: {user_id}...")
    
    try:
        # Thêm timeout để tránh treo
        response = requests.get(f"{INSTAGRAM_API_URL}{user_id}", timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            if isinstance(data, list) and len(data) > 0:
                await status_message.edit_text(f"Tìm thấy {len(data)} bài đăng từ {user_id}")
                
                # Xử lý từng bài post riêng biệt
                post_count = 0
                success_count = 0
                
                for post in data:
                    try:
                        caption = post.get("caption", "")
                        user_info = post.get("user", {})
                        username = user_info.get("username", user_id)
                        full_name = user_info.get("fullName", "")
                        
                        # Tạo caption đầy đủ
                        full_caption = f"📱 {full_name} (@{username})\n\n"
                        if caption:
                            full_caption += f"{caption}\n"
                        
                        # Xử lý media
                        media_list = post.get("media", [])
                        
                        if not media_list:
                            await update.message.reply_text(f"{full_caption}\n(Không có media trong bài đăng này)")
                            continue
                        
                        # Gửi media theo nhóm nếu có nhiều hơn 1 ảnh
                        if len(media_list) > 1:
                            success = await send_media_group_safely(update, media_list, full_caption)
                            if success:
                                success_count += 1
                        else:
                            # Nếu chỉ có 1 media, gửi riêng với caption
                            media = media_list[0]
                            media_url = media.get("url", "")
                            media_type = media.get("type", "").lower()
                            
                            if media_url:
                                try:
                                    if media_type in ["image", "carousel"]:
                                        await update.message.reply_photo(photo=media_url, caption=full_caption)
                                        success_count += 1
                                    elif media_type == "video":
                                        await update.message.reply_video(video=media_url, caption=full_caption)
                                        success_count += 1
                                    else:
                                        # Mặc định xử lý như ảnh
                                        await update.message.reply_photo(photo=media_url, caption=full_caption)
                                        success_count += 1
                                except Exception as single_media_error:
                                    logger.error(f"Lỗi khi gửi media đơn: {single_media_error}")
                                    await update.message.reply_text(f"{full_caption}\n(Không thể hiển thị media: {str(single_media_error)})")
                            else:
                                await update.message.reply_text(f"{full_caption}\n(Không có URL media hợp lệ)")
                        
                        post_count += 1
                        # Delay nhỏ giữa các bài đăng
                        await asyncio.sleep(RATE_LIMIT_DELAY)
                    
                    except Exception as post_error:
                        logger.error(f"Lỗi khi xử lý bài đăng: {post_error}")
                        await update.message.reply_text(f"Lỗi khi xử lý một bài đăng: {str(post_error)}")
                
                # Thông báo tổng kết
                result_message = f"Đã xử lý xong {post_count} bài đăng từ {user_id}"
                if success_count < post_count:
                    result_message += f" (hiển thị thành công {success_count}/{post_count})"
                await update.message.reply_text(result_message)
            else:
                await update.message.reply_text("Không tìm thấy bài đăng nào hoặc dữ liệu không đúng định dạng.")
        else:
            # Thử đọc thông báo lỗi từ phản hồi
            error_msg = f"Lỗi: API trả về mã trạng thái {response.status_code}"
            try:
                error_data = response.json()
                if isinstance(error_data, dict) and ("error" in error_data or "message" in error_data):
                    error_detail = error_data.get("error", error_data.get("message", ""))
                    error_msg += f"\nChi tiết: {error_detail}"
            except:
                pass
            
            await update.message.reply_text(error_msg)
    
    except requests.exceptions.Timeout:
        await update.message.reply_text(f"Yêu cầu API bị timeout. Vui lòng thử lại sau.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kết nối API: {e}")
        await update.message.reply_text(f"Lỗi kết nối đến API: {str(e)}")
    except Exception as e:
        logger.error(f"Lỗi khi lấy bài đăng Instagram: {e}")
        await update.message.reply_text(f"Xin lỗi, đã xảy ra lỗi: {str(e)}")
    finally:
        # Xóa thông báo trạng thái nếu còn tồn tại
        try:
            await status_message.delete()
        except:
            pass

async def get_instagram_post_by_url(update: Update, post_url: str) -> None:
    """Lấy bài đăng Instagram từ URL và gửi dưới dạng ảnh/video."""
    status_message = await update.message.reply_text(f"Đang tìm thông tin cho bài đăng từ URL...")
    
    try:
        # Gọi API để lấy thông tin bài đăng từ URL
        encoded_url = requests.utils.quote(post_url)
        response = requests.get(f"{INSTAGRAM_POST_URL_API}{encoded_url}", timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            
            # Kiểm tra cấu trúc dữ liệu và xử lý
            if isinstance(data, dict):
                # Xử lý dạng đối tượng đơn
                caption = data.get("caption", "")
                user_info = data.get("user", {})
                username = user_info.get("username", "")
                full_name = user_info.get("fullName", "")
                
                # Tạo caption đầy đủ
                full_caption = f"📱 {full_name} (@{username})\n\n"
                if caption:
                    full_caption += f"{caption}\n"
                
                # Xử lý media
                media_list = data.get("media", [])
                
                if media_list:
                    # Gửi media
                    await send_media_group_safely(update, media_list, full_caption)
                else:
                    await update.message.reply_text(f"{full_caption}\n(Không có media trong bài đăng này)")
            
            elif isinstance(data, list) and len(data) > 0:
                # Xử lý dạng danh sách
                post = data[0]  # Lấy phần tử đầu tiên
                
                caption = post.get("caption", "")
                user_info = post.get("user", {})
                username = user_info.get("username", "")
                full_name = user_info.get("fullName", "")
                
                # Tạo caption đầy đủ
                full_caption = f"📱 {full_name} (@{username})\n\n"
                if caption:
                    full_caption += f"{caption}\n"
                
                # Xử lý media
                media_list = post.get("media", [])
                
                if media_list:
                    # Gửi media
                    await send_media_group_safely(update, media_list, full_caption)
                else:
                    await update.message.reply_text(f"{full_caption}\n(Không có media trong bài đăng này)")
            else:
                await update.message.reply_text("Không tìm thấy thông tin về bài đăng này.")
        else:
            await update.message.reply_text(f"Lỗi: API trả về mã trạng thái {response.status_code}")
    
    except Exception as e:
        logger.error(f"Lỗi khi lấy bài đăng từ URL: {e}")
        await update.message.reply_text(f"Xin lỗi, đã xảy ra lỗi khi xử lý URL: {str(e)}")
    finally:
        # Xóa thông báo trạng thái
        try:
            await status_message.delete()
        except:
            pass

async def handle_instagram_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xử lý khi người dùng gửi URL Instagram."""
    message_text = update.message.text
    
    # Các pattern URL Instagram phổ biến
    username_pattern = r'instagram\.com/([^/\?]+)(?:/|\?|$)'
    post_pattern = r'instagram\.com/(?:p|reel|tv)/([^/\?]+)(?:/|\?|$)'
    story_pattern = r'instagram\.com/stories/([^/\?]+)(?:/|\?|$)'
    
    # Kiểm tra URL bài viết (post, reel, tv)
    post_match = re.search(post_pattern, message_text)
    if post_match:
        await get_instagram_post_by_url(update, message_text)
        return
    
    # Kiểm tra URL story
    story_match = re.search(story_pattern, message_text)
    if story_match:
        username = story_match.group(1)
        await update.message.reply_text(f"Tính năng lấy story của @{username} đang được phát triển.")
        return
    
    # Kiểm tra URL profile
    username_match = re.search(username_pattern, message_text)
    if username_match:
        username = username_match.group(1)
        if username not in ["p", "stories", "reel", "tv", "explore"]:  # Loại trừ các path đặc biệt
            # Xử lý như lệnh /getinfo
            context.args = [username]
            await get_instagram_info(update, context)
            return
    
    # Nếu không phù hợp với bất kỳ pattern nào
    await echo(update, context)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Phản hồi tin nhắn người dùng."""
    message_text = update.message.text.lower()
    
    # Kiểm tra một số từ khóa phổ biến để hướng dẫn người dùng
    if any(keyword in message_text for keyword in ["instagram", "insta", "ig"]):
        await update.message.reply_text(
            "Tôi có thể giúp bạn với Instagram! Hãy thử các lệnh sau:\n"
            "/getinfo [username] - Lấy thông tin tài khoản\n"
            "/getpost [username] - Lấy bài đăng gần đây\n"
            "Hoặc gửi trực tiếp URL Instagram để tôi xử lý."
        )
    elif "help" in message_text or "hướng dẫn" in message_text or "trợ giúp" in message_text:
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Tôi không hiểu lệnh đó. Sử dụng /help để xem các lệnh có sẵn."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xử lý lỗi."""
    logger.error(f"Lỗi: {context.error} trong update {update}")
    
    # Gửi thông báo lỗi thân thiện cho người dùng
    error_message = "Đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau."
    
    if update and update.effective_message:
        await update.effective_message.reply_text(error_message)

def extract_username_from_url(url: str) -> Optional[str]:
    """Trích xuất username từ URL Instagram."""
    patterns = [
        r'instagram\.com/([^/\?]+)(?:/|\?|$)',  # instagram.com/username
        r'@([a-zA-Z0-9._]+)'                    # @username
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            username = match.group(1)
            # Loại trừ các path đặc biệt
            if username not in ["p", "stories", "reel", "tv", "explore"]:
                return username
    
    return None

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xử lý tin nhắn văn bản từ người dùng."""
    message_text = update.message.text
    
    # Kiểm tra xem có phải là URL Instagram không
    if "instagram.com" in message_text:
        await handle_instagram_url(update, context)
        return
    
    # Kiểm tra xem có phải là username Instagram với @ không
    username_match = re.search(r'^@([A-Za-z0-9._]+)$', message_text)
    if username_match:
        username = username_match.group(1)
        context.args = [username]
        await get_instagram_info(update, context)
        return
    
    # Chuyển sang xử lý thông thường
    await echo(update, context)

def main() -> None:
    """Khởi động bot."""
    # Tạo ứng dụng
    application = Application.builder().token(TOKEN).build()

    # Thêm các bộ xử lý lệnh
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("getpost", get_instagram_post))
    application.add_handler(CommandHandler("getinfo", get_instagram_info))
    
    # Thêm bộ xử lý cho tin nhắn văn bản
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    
    # Thêm bộ xử lý lỗi
    application.add_error_handler(error_handler)

    # Thông báo khi bot bắt đầu
    logger.info("Bot Instagram đã sẵn sàng và bắt đầu polling...")
    
    # Chạy bot cho đến khi người dùng nhấn Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()