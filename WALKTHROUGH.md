# Gmail OTP অ্যাকাউন্ট ভেরিফিকেশন সিস্টেম — ওয়াকথ্রু (Walkthrough)

আমরা সিস্টেমে অন্য কোনো অপ্রয়োজনীয় ফাইলে হাত না দিয়ে শুধুমাত্র অ্যাকাউন্ট তৈরির প্রক্রিয়াটি আপডেট করেছি। এখন ব্যবহারকারী সাইন-আপ করার সময় তার জিমেইলে একটি ৬-সংখ্যার ওটিপি (OTP) ভেরিফিকেশন কোড যাবে এবং কোডটি দিয়ে কনফার্ম করলে রিকোয়েস্ট Admin approval এর জন্য পেন্ডিং থাকবে (সরাসরি অ্যাকাউন্ট তৈরি হয় না)।

---

## 🛠️ বাস্তবায়িত পরিবর্তনসমূহ

### ১. `.env` কনফিগারেশন ফাইল ([`.env`](file:///f:/DBMS%20LAB%20PROJECT/DBMS-LAB-PROJECT-RESEARCH-MANAGEMENT-SYSTEM/.env))
প্রেরক জিমেইল এবং গুগল অ্যাপ পাসওয়ার্ড সেট করার জন্য কনফিগ ফাইল তৈরি করা হয়েছে:
```env
GMAIL_SENDER_EMAIL=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_digit_app_password
```
*(নোট: টেস্টিং সুবিধার জন্য জিমেইল ক্রেডেনশিয়াল না থাকলেও ব্যাকএন্ড কনসোলে কোডটি প্রিন্ট হবে, ফলে টেস্টিং বাধাগ্রস্ত হবে না)*।

### ২. ব্যাকএন্ড স্কিমা স্তর ([`schemas.py`](file:///f:/DBMS%20LAB%20PROJECT/DBMS-LAB-PROJECT-RESEARCH-MANAGEMENT-SYSTEM/schemas.py))
* নতুন স্কিমা `SendOTPRequest`: ওটিপি রিকোয়েস্টের জন্য ইমেইল ভ্যালিডেশন।
* `FacultyCreate` ও `AdminCreate` স্কিমাতে `otp: Optional[str] = None` যোগ করা হয়েছে।

### ৩. বিজনেস লজিক ও ইমেইল সার্ভিস ([`crud.py`](file:///f:/DBMS%20LAB%20PROJECT/DBMS-LAB-PROJECT-RESEARCH-MANAGEMENT-SYSTEM/crud.py))
* `OTP_STORE`: ইন-মেমোরি ওটিপি ক্যাশিং ডিকশনারি (মেয়াদ: ১০ মিনিট, রেট-লিমিট: ৬০ সেকেন্ডে ১টি, ঘণ্টায় সর্বোচ্চ ৫টি)।
* `send_verification_otp(db, email)`: ডুপ্লিকেট ইমেইল চেক করে, ৬ সংখ্যার র‍্যান্ডম কোড তৈরি করে এবং Gmail SMTP (`smtp.gmail.com:587`) দিয়ে প্রফেশনাল HTML ইমেইল টেমপ্লেটে কোড পাঠায়।
* `verify_otp(email, otp)`: ইনপুট দেওয়া কোডটি যাচাই করে সঠিক হলে মুছে ফেলে।

### ৪. ব্যাকএন্ড এন্ডপয়েন্ট ([`NiazBackend.py`](file:///f:/DBMS%20LAB%20PROJECT/DBMS-LAB-PROJECT-RESEARCH-MANAGEMENT-SYSTEM/NiazBackend.py))
* `POST /auth/send-otp`: জিমেইলে ভেরিফিকেশন কোড পাঠানোর এন্ডপয়েন্ট।
* `POST /auth/signup/faculty`: ওটিপি যাচাই করে `crud.request_faculty_signup` দিয়ে Admin approval এর জন্য পেন্ডিং নোটিফিকেশন তৈরি করে।
* `POST /auth/signup/admin`: ওটিপি যাচাই করে `crud.request_admin_signup` দিয়ে Admin approval এর জন্য পেন্ডিং নোটিফিকেশন তৈরি করে।
* `POST /auth/signup/student`: ওটিপি যাচাই করে `crud.request_student_signup` দিয়ে Admin approval এর জন্য পেন্ডিং নোটিফিকেশন তৈরি করে।

### ৫. ফ্রন্টএন্ড ইউজার ইন্টারফেস ([`frontend.html`](file:///f:/DBMS%20LAB%20PROJECT/DBMS-LAB-PROJECT-RESEARCH-MANAGEMENT-SYSTEM/frontend.html))
* **নতুন ওটিপি ভেরিফিকেশন মডাল (`#otp-modal`):** ৬ ডিজিটের কোড দেওয়ার জন্য বড় ফন্টের ইনপুট বক্স, "Verify & Create Account" বাটন এবং "Resend Code" ফিচার যুক্ত করা হয়েছে।
* **`handleSignup` ও `submitOtpVerification`:** সাইন-আপ ফর্মে ক্লিক করলে ব্যাকএন্ডে ওটিপি রিকোয়েস্ট যায়, পপ-আপ মডাল আসে এবং ওটিপি দিয়ে ভেরিফাই সম্পন্ন হলে সফলতার নোটিফিকেশন প্রদর্শন করে সরাসরি লগইন পেজে নিয়ে যায়।

---

## 🧪 ভেরিফিকেশন ফলাফল

1. **পাইথন কম্পাইলেশন ও সিনট্যাক্স যাচাই:**
   - `python -m py_compile NiazBackend.py crud.py schemas.py` সফলভাবে ০ কোডে সম্পন্ন হয়েছে।
2. **ওটিপি লজিক ও ভ্যালিডেশন টেস্ট:**
   - `crud.verify_otp` মেথড ইন-মেমোরি ক্যাশ এবং এক্সপায়ারি টাইমের সাথে সফলভাবে টেস্ট করা হয়েছে (Exit code: 0)।
3. **সার্ভার স্টার্টআপ টেস্ট:**
   - `FastAPI` অ্যাপ `NiazBackend` সফলভাবে লোড হয়েছে (Exit code: 0)।
