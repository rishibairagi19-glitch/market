from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from supabase import create_client, Client
from werkzeug.utils import secure_filename
import os
import io
import random
import traceback
import html
import urllib.parse
from PIL import Image
from dotenv import load_dotenv

# Vercel के लिए फोल्डर का सही (Absolute) पाथ सेट करें (अब सभी फाइलें बाहर ही हैं)
base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=base_dir, static_folder=base_dir)

load_dotenv()

# सेशन के लिए एक सीक्रेट की सेट करें (लॉगिन सुरक्षित रखने के लिए)
app.secret_key = os.getenv("SECRET_KEY", "my_super_secret_key")

# Supabase क्रेडेंशियल्स सेट करें
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vercel पर 500 Error को स्क्रीन पर विस्तार से दिखाने के लिए
@app.errorhandler(Exception)
def handle_exception(e):
    error_trace = traceback.format_exc()
    return f"<h2 style='color:red;'>Application Error (500)</h2><p>कृपया इस एरर को कॉपी करें और मुझे बताएं:</p><pre style='background:#f4f4f4; padding:15px; border:1px solid #ddd; overflow-x:auto;'>{error_trace}</pre>", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/", methods=["GET", "POST"])
def index():
    success_msg = None
    active_admin_tab = "home_tab"
    active_tab = "login"

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "signup":
            owner_name = request.form.get("owner_name", "").strip()
            shop_name = request.form.get("shop_name", "").strip().replace(" ", "-")
            mobile_number = request.form.get("mobile_number", "").strip()
            password = request.form.get("password")
            main_category = request.form.get("main_category")
            category = request.form.get("category")
            
            # चेक करें कि दुकान का नाम या मोबाइल नंबर पहले से मौजूद तो नहीं है
            existing_shop = supabase.table("shop_owners").select("*").eq("shop_name", shop_name).execute()
            if existing_shop.data:
                return render_template("index.html", error="<span class='lang-text' data-hi='यह दुकान का नाम पहले से किसी ने ले लिया है। कृपया कोई और नाम चुनें!' data-en='This shop name is already taken. Please choose another!'>यह दुकान का नाम पहले से किसी ने ले लिया है। कृपया कोई और नाम चुनें!</span>", active_tab="signup")
                
            existing_mobile = supabase.table("shop_owners").select("*").eq("mobile_number", mobile_number).execute()
            if existing_mobile.data:
                return render_template("index.html", error="<span class='lang-text' data-hi='यह मोबाइल नंबर पहले से रजिस्टर है। कृपया लॉगिन करें या दूसरा नंबर चुनें!' data-en='This mobile number is already registered. Please login or choose another!'>यह मोबाइल नंबर पहले से रजिस्टर है। कृपया लॉगिन करें या दूसरा नंबर चुनें!</span>", active_tab="signup")
                
            # 7-डिजिट की यूनिक ID जनरेट करें (जो पहले से डेटाबेस में न हो)
            while True:
                shop_id = random.randint(1000000, 9999999)
                check_id = supabase.table("shop_owners").select("shop_id").eq("shop_id", shop_id).execute()
                if not check_id.data:
                    break

            # Supabase में नया यूज़र (दुकानदार) सेव करें
            try:
                supabase.table("shop_owners").insert({
                    "owner_name": owner_name,
                    "shop_name": shop_name,
                    "mobile_number": mobile_number,
                    "password": password,
                    "shop_id": shop_id,
                    "main_category": main_category,
                    "category": category
                }).execute()
            except Exception as e:
                # अगर डेटाबेस में 'main_category' कॉलम नहीं है, तो उसके बिना सेव करें ताकि ऐप क्रैश न हो
                if "main_category" in str(e):
                    try:
                        supabase.table("shop_owners").insert({
                            "owner_name": owner_name,
                            "shop_name": shop_name,
                            "mobile_number": mobile_number,
                            "password": password,
                            "shop_id": shop_id,
                            "category": category
                        }).execute()
                    except Exception as fallback_e:
                        return render_template("index.html", error=f"डेटाबेस एरर: {html.escape(str(fallback_e))}", active_tab="signup")
                else:
                    return render_template("index.html", error=f"साइन-अप एरर: {html.escape(str(e))}", active_tab="signup")
            
            success_msg = f"<span class='lang-text' data-hi='साइन-अप सफल रहा! आपकी 7-डिजिट की शॉप ID <b>{shop_id}</b> है। आप इस ID या अपने मोबाइल नंबर से लॉगिन कर सकते हैं।' data-en='Sign-up successful! Your 7-digit Shop ID is <b>{shop_id}</b>. You can login using this ID or your mobile number.'>साइन-अप सफल रहा! आपकी 7-डिजिट की शॉप ID <b>{shop_id}</b> है। आप इस ID या अपने मोबाइल नंबर से लॉगिन कर सकते हैं।</span>"
            return render_template("index.html", success=success_msg, active_tab="login")
            
        elif action == "login":
            login_id = request.form.get("login_id", "").strip()
            password = request.form.get("password")
            
            # यूज़र को ID या मोबाइल नंबर से ढूँढें
            user_data = None
            user_res = supabase.table("shop_owners").select("*").eq("mobile_number", login_id).execute()
            if user_res.data:
                user_data = user_res.data[0]
            elif login_id.isdigit() and len(login_id) == 7:
                user_res = supabase.table("shop_owners").select("*").eq("shop_id", int(login_id)).execute()
                if user_res.data:
                    user_data = user_res.data[0]
            
            if not user_data:
                return render_template("index.html", error="<span class='lang-text' data-hi='यह मोबाइल नंबर या ID रजिस्टर नहीं है। कृपया पहले साइन-अप करें।' data-en='This mobile number or ID is not registered. Please sign up first.'>यह मोबाइल नंबर या ID रजिस्टर नहीं है। कृपया पहले साइन-अप करें।</span>", active_tab="login")
                
            if user_data["password"] != password:
                return render_template("index.html", error="<span class='lang-text' data-hi='पासवर्ड गलत है। कृपया सही पासवर्ड दर्ज करें।' data-en='Incorrect password. Please enter the correct password.'>पासवर्ड गलत है। कृपया सही पासवर्ड दर्ज करें।</span>", active_tab="login")
            
            # अगर सब सही है
            session["owner_name"] = user_data["owner_name"]
            session["shop_name"] = user_data["shop_name"]
            session["shop_id"] = user_data.get("shop_id")
            session["main_category"] = user_data.get("main_category", "")
            session["category"] = user_data.get("category", "general")
            return redirect(url_for("index"))
                
        elif action == "add_product":
            shop_name = session.get("shop_name")
            if not shop_name:
                return redirect(url_for("index"))
            owner_name = session.get("owner_name", "Unknown")
            product = request.form.get("product")
            price = request.form.get("price")
            size = request.form.get("size")
            quantity = request.form.get("quantity")
            product_category = request.form.get("product_category", "General")
            
            # अगर यूजर ने 'नई केटेगरी' चुनी है, तो नए इनपुट बॉक्स का डाटा लें
            if product_category == "__NEW__":
                product_category = request.form.get("new_product_category", "General").strip().title()
            else:
                product_category = product_category.title()
        
            # 1. एक से ज़्यादा इमेज अपलोड हैंडल करना (Multiple Images)
            images = request.files.getlist("product_image")
            image_paths = []
            for image in images:
                if image and image.filename:
                    filename = secure_filename(image.filename)
                    base_name = os.path.splitext(filename)[0]
                    unique_filename = f"{random.randint(10000, 99999)}_{base_name}.webp"
                    
                    try:
                        # प्रोडक्ट इमेज का साइज कम (Compress) करने के लिए Pillow का उपयोग
                        img = Image.open(image)
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        img.thumbnail((600, 600))  # अधिकतम साइज 600x600 (फास्ट अपलोड के लिए)
                        
                        # इमेज को मेमोरी (BytesIO) में सेव करें
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='WEBP', quality=60) # WebP: JPEG से 50% अधिक हल्का और फास्ट
                        img_bytes = img_byte_arr.getvalue()
                        
                        # Supabase Storage में अपलोड करें (बकेट: img-market)
                        supabase.storage.from_("img-market").upload(
                            file=img_bytes,
                            path=f"products/{unique_filename}",
                            file_options={"content-type": "image/webp"}
                        )
                        # पब्लिक URL प्राप्त करें
                        public_url = supabase.storage.from_("img-market").get_public_url(f"products/{unique_filename}")
                        image_paths.append(public_url)
                    except Exception as e:
                        print(f"Error processing or uploading image: {e}")
                        continue # अगर कोई करप्टेड इमेज हो तो उसे छोड़कर आगे बढ़ें
            
            image_url_string = ",".join(image_paths) # सभी इमेज URL को कॉमा से जोड़ दें

            try:
                # 2. दुकान के लिए QR कोड (API के जरिए)
                safe_shop_name = urllib.parse.quote(shop_name)
                shop_url = f"{request.host_url}shop/{safe_shop_name}"
                safe_shop_url = urllib.parse.quote(shop_url, safe=':/?=&')
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={safe_shop_url}"

                # 3. प्रोडक्ट के लिए यूनिक ID बनाएं
                while True:
                    product_id = f"PRD{random.randint(10000, 99999)}"
                    check_pid = supabase.table("shops").select("product_id").eq("product_id", product_id).execute()
                    if not check_pid.data:
                        break

                # Supabase में डेटा डालें
                data = supabase.table("shops").insert({
                    "owner_name": owner_name,
                    "shop_name": shop_name,
                    "product_id": product_id,
                    "product": product,
                    "product_category": product_category,
                    "price": price,
                    "size": size,
                    "quantity": quantity,
                    "description": request.form.get("description", ""),
                    "warranty": request.form.get("warranty", ""),
                    "replacement": request.form.get("replacement", ""),
                    "image_url": image_url_string,
                    "qr_code_url": qr_url
                }).execute()
                
                success_msg = f"<span class='lang-text' data-hi='प्रोडक्ट सफलतापूर्वक सेव हो गया! आपकी शॉप का लिंक: <a href=\"/shop/{shop_name}\">{shop_url}</a> <br><br> QR कोड: <br><img src=\"{qr_url}\" width=\"150\">' data-en='Product saved successfully! Your shop link: <a href=\"/shop/{shop_name}\">{shop_url}</a> <br><br> QR Code: <br><img src=\"{qr_url}\" width=\"150\">'>प्रोडक्ट सफलतापूर्वक सेव हो गया! आपकी शॉप का लिंक: <a href='/shop/{shop_name}'>{shop_url}</a> <br><br> QR कोड: <br><img src='{qr_url}' width='150'></span>"
                active_admin_tab = "manage_products_tab"
            except Exception as e:
                error_msg = f"<span class='lang-text' data-hi='प्रोडक्ट सेव करते समय डेटाबेस एरर: {html.escape(str(e))}' data-en='Database error while saving product: {html.escape(str(e))}'>प्रोडक्ट सेव करते समय डेटाबेस एरर: {html.escape(str(e))}</span>"
                return render_template("index.html", error=error_msg)

        elif action == "delete_product":
            shop_name = session.get("shop_name")
            if not shop_name:
                return redirect(url_for("index"))
            product_id = request.form.get("product_id")
            try:
                supabase.table("shops").delete().eq("product_id", product_id).eq("shop_name", shop_name).execute()
                success_msg = "<span class='lang-text' data-hi='प्रोडक्ट सफलतापूर्वक डिलीट हो गया!' data-en='Product deleted successfully!'>प्रोडक्ट सफलतापूर्वक डिलीट हो गया!</span>"
                active_admin_tab = "manage_products_tab"
            except Exception as e:
                return render_template("index.html", error=f"डिलीट करते समय एरर: {html.escape(str(e))}")

        elif action == "edit_product":
            shop_name = session.get("shop_name")
            if not shop_name:
                return redirect(url_for("index"))
            product_id = request.form.get("product_id")
            try:
                product_category = request.form.get("product_category", "General")
                
                if product_category == "__NEW__":
                    product_category = request.form.get("new_product_category", "General").strip().title()
                else:
                    product_category = product_category.title()
                    
                supabase.table("shops").update({
                    "product": request.form.get("product"),
                    "price": request.form.get("price"),
                    "size": request.form.get("size"),
                    "product_category": product_category,
                    "quantity": request.form.get("quantity"),
                    "description": request.form.get("description", ""),
                    "warranty": request.form.get("warranty", ""),
                    "replacement": request.form.get("replacement", "")
                }).eq("product_id", product_id).eq("shop_name", shop_name).execute()
                success_msg = "<span class='lang-text' data-hi='प्रोडक्ट सफलतापूर्वक अपडेट हो गया!' data-en='Product updated successfully!'>प्रोडक्ट सफलतापूर्वक अपडेट हो गया!</span>"
                active_admin_tab = "manage_products_tab"
            except Exception as e:
                return render_template("index.html", error=f"अपडेट करते समय एरर: {html.escape(str(e))}")
                
        elif action == "update_order":
            shop_name = session.get("shop_name")
            if not shop_name:
                return redirect(url_for("index"))
            order_id = request.form.get("order_id")
            new_status = request.form.get("status")
            try:
                supabase.table("orders").update({"status": new_status}).eq("id", order_id).eq("shop_name", shop_name).execute()
                success_msg = "<span class='lang-text' data-hi='ऑर्डर स्टेटस अपडेट हो गया!' data-en='Order status updated!'>ऑर्डर स्टेटस अपडेट हो गया!</span>"
                active_admin_tab = "orders_tab"
            except Exception as e:
                return render_template("index.html", error=f"ऑर्डर अपडेट करते समय एरर: {html.escape(str(e))}")
                
        elif action == "edit_profile":
            shop_name = session.get("shop_name")
            if not shop_name:
                return redirect(url_for("index"))
            new_owner_name = request.form.get("owner_name", "").strip()
            new_shop_name = request.form.get("shop_name", "").strip().replace(" ", "-")
            new_mobile = request.form.get("mobile_number", "").strip()
            new_main_category = request.form.get("main_category")
            new_category = request.form.get("category")
            new_password = request.form.get("password")
            profile_pic = request.files.get("profile_pic")
            
            try:
                # चेक करें कि नया मोबाइल नंबर किसी और दुकान का तो नहीं है
                existing = supabase.table("shop_owners").select("shop_name").eq("mobile_number", new_mobile).execute()
                if existing.data and existing.data[0]["shop_name"] != shop_name:
                    return render_template("index.html", error="<span class='lang-text' data-hi='यह मोबाइल नंबर पहले से किसी और के पास रजिस्टर है!' data-en='This mobile number is registered with someone else!'>यह मोबाइल नंबर पहले से किसी और के पास रजिस्टर है!</span>", active_admin_tab="profile_tab")
                
                # चेक करें कि नया दुकान का नाम पहले से किसी ने ले तो नहीं लिया
                if new_shop_name and new_shop_name != shop_name:
                    existing_shop = supabase.table("shop_owners").select("shop_name").eq("shop_name", new_shop_name).execute()
                    if existing_shop.data:
                        return render_template("index.html", error="<span class='lang-text' data-hi='यह दुकान का नाम पहले से किसी ने ले लिया है!' data-en='This shop name is already taken!'>यह दुकान का नाम पहले से किसी ने ले लिया है!</span>", active_admin_tab="profile_tab")

                update_data = {
                    "owner_name": new_owner_name,
                    "shop_name": new_shop_name if new_shop_name else shop_name,
                    "mobile_number": new_mobile,
                    "main_category": new_main_category,
                    "category": new_category
                }
                
                if new_password:
                    update_data["password"] = new_password
                
                if profile_pic and profile_pic.filename:
                    pic_filename = secure_filename(profile_pic.filename)
                    base_pic_name = os.path.splitext(pic_filename)[0]
                    unique_pic_name = f"profile_{random.randint(10000, 99999)}_{base_pic_name}.webp"
                    
                    try:
                        # प्रोफाइल फोटो को 1:1 (Square) में क्रॉप करें और साइज कम करें
                        img = Image.open(profile_pic)
                        width, height = img.size
                        min_dim = min(width, height) # चौड़ाई या ऊँचाई में से जो कम हो, उसे चुनें
                        
                        left = (width - min_dim) / 2
                        top = (height - min_dim) / 2
                        right = (width + min_dim) / 2
                        bottom = (height + min_dim) / 2
                        img_cropped = img.crop((left, top, right, bottom)) # बीच से 1:1 क्रॉप करें
                        
                        if img_cropped.mode in ("RGBA", "P"):
                            img_cropped = img_cropped.convert("RGB")
                        img_cropped.thumbnail((300, 300)) # प्रोफाइल के लिए 300x300 बहुत है
                        
                        # इमेज को मेमोरी (BytesIO) में सेव करें
                        img_byte_arr = io.BytesIO()
                        img_cropped.save(img_byte_arr, format='WEBP', quality=70)
                        img_bytes = img_byte_arr.getvalue()
                        
                        # Supabase Storage में अपलोड करें
                        supabase.storage.from_("img-market").upload(
                            file=img_bytes,
                            path=f"profiles/{unique_pic_name}",
                            file_options={"content-type": "image/webp"}
                        )
                        public_url = supabase.storage.from_("img-market").get_public_url(f"profiles/{unique_pic_name}")
                        update_data["profile_pic_url"] = public_url
                    except Exception as e:
                        print(f"Error processing or uploading profile pic: {e}")
                
                try:
                    supabase.table("shop_owners").update(update_data).eq("shop_name", shop_name).execute()
                    
                    # अगर दुकान का नाम बदला गया है, तो Products और Orders टेबल में भी अपडेट करें
                    if new_shop_name and new_shop_name != shop_name:
                        safe_shop_url = urllib.parse.quote(f"{request.host_url}shop/{urllib.parse.quote(new_shop_name)}", safe=':/?=&')
                        new_qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={safe_shop_url}"
                        
                        supabase.table("shops").update({"shop_name": new_shop_name, "qr_code_url": new_qr_url}).eq("shop_name", shop_name).execute()
                        supabase.table("orders").update({"shop_name": new_shop_name}).eq("shop_name", shop_name).execute()
                        session["shop_name"] = new_shop_name
                        shop_name = new_shop_name
                except Exception as e:
                    # प्रोफाइल अपडेट में भी फॉलबैक लगाएँ
                    if "main_category" in str(e):
                        update_data.pop("main_category", None)
                        supabase.table("shop_owners").update(update_data).eq("shop_name", shop_name).execute()
                    else:
                        raise e
                
                session["owner_name"] = new_owner_name
                session["main_category"] = new_main_category
                session["category"] = new_category
                success_msg = "<span class='lang-text' data-hi='प्रोफाइल सफलतापूर्वक अपडेट हो गई!' data-en='Profile updated successfully!'>प्रोफाइल सफलतापूर्वक अपडेट हो गई!</span>"
                active_admin_tab = "profile_tab"
            except Exception as e:
                return render_template("index.html", error=f"प्रोफाइल अपडेट करते समय एरर: {html.escape(str(e))}", active_admin_tab="profile_tab")
        
    # अगर यूज़र लॉगिन है तो उसकी प्रोफाइल और प्रोडक्ट डेटा लाएं
    user_products = []
    user_profile = {}
    user_orders = []
    qr_url = ""
    if "shop_name" in session:
        shop_name = session["shop_name"]
        
        # QR कोड (API के जरिए)
        safe_shop_name = urllib.parse.quote(shop_name)
        shop_url = f"{request.host_url}shop/{safe_shop_name}"
        safe_shop_url = urllib.parse.quote(shop_url, safe=':/?=&')
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={safe_shop_url}"
            
        prod_res = supabase.table("shops").select("*").eq("shop_name", shop_name).execute()
        user_products = prod_res.data
        if user_products:
            for p in user_products:
                p["product_category"] = (p.get("product_category") or "General").title()

        prof_res = supabase.table("shop_owners").select("*").eq("shop_name", shop_name).execute()
        if prof_res.data:
            user_profile = prof_res.data[0]
            
        try:
            order_res = supabase.table("orders").select("*").eq("shop_name", shop_name).order("id", desc=True).execute()
            user_orders = order_res.data
        except Exception:
            pass # In case the orders table hasn't been created yet
            
    return render_template("index.html", user_products=user_products, user_profile=user_profile, user_orders=user_orders, success=success_msg, active_admin_tab=active_admin_tab, active_tab=active_tab, qr_url=qr_url)

@app.route("/api/place_order", methods=["POST"])
def api_place_order():
    data = request.json or {}
    try:
        supabase.table("orders").insert({
            "shop_name": data.get("shop_name"),
            "customer_name": data.get("customer_name"),
            "customer_mobile": data.get("customer_mobile"),
            "order_details": data.get("order_details"),
            "total_amount": data.get("total_amount"),
            "status": "Pending"
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 3. पब्लिक शॉप पेज (जिसे QR स्कैन करके ग्राहक देखेंगे)
@app.route("/shop/<shop_name>")
def view_shop(shop_name):
    # दुकान की केटेगरी लाएं ताकि ग्राहकों को सही लेबल दिखे
    owner_res = supabase.table("shop_owners").select("category", "mobile_number", "views_count").eq("shop_name", shop_name).execute()
    
    if not owner_res.data:
        return f"<h2 style='text-align:center; margin-top:50px; font-family:sans-serif;'>दुकान '{html.escape(shop_name)}' नहीं मिली (Shop Not Found) 😕</h2><p style='text-align:center;'><a href='/'>होम पेज पर जाएं</a></p>", 404
    
    # दुकान के व्यूज़ (Views) बढ़ाएं
    if owner_res.data:
        current_views = owner_res.data[0].get("views_count") or 0
        try:
            supabase.table("shop_owners").update({"views_count": current_views + 1}).eq("shop_name", shop_name).execute()
        except Exception:
            pass

    # Supabase से इस दुकान के प्रोडक्ट्स लाएं
    response = supabase.table("shops").select("*").eq("shop_name", shop_name).execute()
    products = response.data
    if products:
        for p in products:
            p["product_category"] = (p.get("product_category") or "General").title()
    
    # प्रोडक्ट्स की यूनीक केटेगरी निकालें
    product_categories = sorted(list(set([p.get("product_category") or "General" for p in products])))

    shop_category = owner_res.data[0].get("category", "general") if owner_res.data else "general"
    shop_mobile = owner_res.data[0].get("mobile_number", "") if owner_res.data else ""
    
    return render_template("index.html", is_shop_view=True, shop_name=shop_name, products=products, product_categories=product_categories, shop_category=shop_category, shop_mobile=shop_mobile)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
