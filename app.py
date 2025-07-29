from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import os
import sqlite3
from datetime import datetime

app = Flask(__name__, template_folder='templates')
app.secret_key = os.urandom(24) # Used for Flask sessions, essential for security

# --- SQLite Database Configuration ---
DATABASE = 'users.db' # The name of your SQLite database file

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row # This allows accessing columns by name
    return conn

def init_db():
    """Initializes the database by creating the users table if it doesn't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, -- In a real app, store hashed passwords!
                member_since TEXT NOT NULL
            )
        ''')
        conn.commit()
    print(f"SQLite database '{DATABASE}' initialized.")

# Initialize the database when the application starts
with app.app_context():
    init_db()

# --- Global variable to track consecutive errors (for chatbot replies) ---
consecutive_errors = 0

# --- Middleware-like function to check authentication ---
@app.before_request
def check_auth():
    # Define routes that do NOT require authentication
    if request.path in ['/login', '/register', '/login_user', '/register_user', '/static/style.css', '/static/script.js']:
        return # Allow access to these pages

    # For all other pages, check if user is authenticated
    if 'user_id' not in session:
        # If not authenticated, redirect to login page
        if request.endpoint != 'login_page': # Avoid infinite redirect if already on login page
            return redirect(url_for('login_page'))

# --- Routes for HTML Pages ---
@app.route("/")
def home():
    # If authenticated, redirect to the main chatbot application
    if 'user_id' in session:
        return redirect(url_for('chat_app_page'))
    return redirect(url_for('login_page')) # Otherwise, go to login

@app.route("/login")
def login_page():
    if 'user_id' in session:
        return redirect(url_for('chat_app_page')) # If already logged in, go to chat
    return render_template("login.html")

@app.route("/register")
def register_page():
    if 'user_id' in session:
        return redirect(url_for('chat_app_page')) # If already logged in, go to chat
    return render_template("register.html")

@app.route("/profile")
def profile_page():
    # Authentication check is handled by @app.before_request
    return render_template("profile.html")

@app.route("/chat_app") # New route for the actual chatbot
def chat_app_page():
    # Authentication check is handled by @app.before_request
    return render_template("chat_app.html") # Your main chatbot frontend is now chat_app.html

# --- API Endpoints for Authentication ---
@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    username = data.get("username")

    if not email or not password or not username:
        return jsonify({"message": "Email, password, and username are required."}), 400
    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters long."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if email or username already exists
        cursor.execute("SELECT id FROM users WHERE email = ? OR username = ?", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({"message": "Email or username already registered."}), 409

        # In a real application, you would hash the password before storing it
        # For simplicity in this example, we store it as plain text.
        # Use libraries like bcrypt for secure password hashing.
        
        member_since = datetime.now().strftime('%B %Y') # e.g., "July 2025"
        
        cursor.execute(
            "INSERT INTO users (username, email, password, member_since) VALUES (?, ?, ?, ?)",
            (username, email, password, member_since)
        )
        conn.commit()
        print(f"User '{username}' registered successfully.")
        return jsonify({"message": "Registration successful! Please log in."}), 201

    except sqlite3.Error as e:
        conn.rollback()
        print(f"SQLite error during registration: {e}")
        return jsonify({"message": f"Registration failed: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Retrieve user by email
        cursor.execute("SELECT id, username, email, password FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if user:
            # In a real app, you'd compare hashed passwords using bcrypt.
            # For this example, we're comparing plain text passwords.
            if user['password'] == password:
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['username'] = user['username'] # Store username in session
                print(f"User '{user['username']}' logged in successfully.")
                return jsonify({"message": "Login successful!"}), 200
            else:
                return jsonify({"message": "Invalid email or password."}), 401
        else:
            return jsonify({"message": "Invalid email or password."}), 401

    except sqlite3.Error as e:
        print(f"SQLite error during login: {e}")
        return jsonify({"message": "Login failed. Please try again."}), 500
    finally:
        conn.close()

@app.route("/logout_user", methods=["POST"])
def logout_user():
    session.pop('user_id', None)
    session.pop('user_email', None)
    session.pop('username', None)
    return jsonify({"message": "Logged out successfully."}), 200

@app.route("/get_user_profile", methods=["GET"])
def get_user_profile():
    if 'user_id' not in session:
        return jsonify({"message": "Not authenticated."}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username, email, member_since FROM users WHERE id = ?", (user_id,))
        profile_data = cursor.fetchone()

        if profile_data:
            return jsonify({
                "username": profile_data['username'],
                "email": profile_data['email'],
                "member_since": profile_data['member_since'],
                "account_type": "Standard User" # Static for now
            }), 200
        else:
            return jsonify({"message": "Profile data not found."}), 404
    except sqlite3.Error as e:
        print(f"SQLite error fetching user profile: {e}")
        return jsonify({"message": "Failed to fetch profile data."}), 500
    finally:
        conn.close()

# --- Chatbot Logic (remains mostly the same, now protected by session and with emojis) ---
@app.route("/chat", methods=["POST"])
def chat():
    global consecutive_errors

    user_message = request.json.get("message", "").lower().strip()

    if not user_message:
        consecutive_errors = 0
        return jsonify({"reply": "Please tell me your career ambition or what you'd like to know! 🤔"}) # Added emoji

    if any(greeting_word in user_message for greeting_word in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "good night", "how are you", "what's up", "greetings"]):
        consecutive_errors = 0
        reply = "Hello there! 👋 I'm a student guidance chatbot. Are you looking for tech-based job opportunities or upskilling roadmaps? 🚀" # Added emojis
        return jsonify({"reply": reply})

    elif user_message in ["yes", "yeah", "yep", "yup", "sure", "definitely"]:
        consecutive_errors = 0
        reply = "Great! ✨ To help you better, what specific tech job or area are you interested in? For example, 'web developer', 'data scientist', 'cybersecurity', or 'software tester'? 💡" # Added emojis
        return jsonify({"reply": reply})

    elif user_message in ["no", "nope", "not really", "nah"]:
        consecutive_errors = 0
        reply = "Okay, no problem! 😊 Is there anything else I can assist you with today, perhaps general information about IT fields or learning resources? 📚" # Added emojis
        return jsonify({"reply": reply})

    elif "thanks" in user_message or "thank you" in user_message or "ty" in user_message:
        consecutive_errors = 0
        reply = "You're welcome! 🙏 Is there anything else I can help you with regarding tech careers or learning paths? 🎓" # Added emojis
        return jsonify({"reply": reply})

    elif "job opportunities after bca" in user_message or "jobs after bca" in user_message or "career after bca" in user_message:
        consecutive_errors = 0
        reply = """After BCA, you have diverse job opportunities in IT! 🌟 Some common roles include:
        - Software Developer / Engineer 💻
        - Web Developer (Frontend, Backend, Full-Stack) 🌐
        - Data Analyst / Data Scientist 📊
        - Cybersecurity Analyst 🔒
        - Cloud Engineer / DevOps Engineer ☁️
        - Database Administrator / DBMS Engineer 🗄️
        - IT Support Specialist 🛠️
        - Systems Analyst 📈
        - App Developer (Android/iOS) 📱
        - Technical Content Writer ✍️
        - Software Tester / QA Engineer 🧪
        - Machine Learning Engineer / AI Engineer 🧠
        - IoT Developer 🔗
        - Android Developer 🤖
        - iOS Developer 🍎
        - Blockchain Developer ⛓️
        - Educator / Teacher 🧑‍🏫
        - Flutter Developer 🦋
        Would you like a roadmap for any of these, or more details on a specific role? 👇""" # Added emojis
        return jsonify({"reply": reply})

    elif "web developer" in user_message or "web dev" in user_message or "frontend" in user_message or "backend" in user_message:
        consecutive_errors = 0
        reply = """A **Web Developer** builds and maintains websites. 🌐
        **Key Skills:** HTML, CSS, JavaScript (for frontend), Python/Node.js/PHP (for backend), database knowledge (SQL/NoSQL), frameworks (React, Angular, Vue, Django, Express), Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Foundations:** HTML, CSS, JavaScript basics (2-4 months) 📚
        2.  **Frontend Deep Dive:** Choose a framework (React/Vue/Angular) (3-6 months) ✨
        3.  **Backend Basics:** Learn a language/framework (Node.js/Python Flask/Django) (3-5 months) ⚙️
        4.  **Databases:** SQL (e.g., PostgreSQL) and maybe NoSQL (e.g., MongoDB) (1-2 months) 🗄️
        5.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        6.  **Build Projects!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "data scientist" in user_message or "data analyst" in user_message or "data science" in user_message:
        consecutive_errors = 0
        reply = """A **Data Analyst/Scientist** extracts insights from data to aid decision-making. 📊
        **Key Skills:** Python (Pandas, NumPy, Matplotlib), R, SQL, Statistics, Data Visualization, Machine Learning fundamentals.
        **Typical Roadmap (Estimated Time):**
        1.  **Programming:** Python fundamentals with data libraries (2-4 months) 🐍
        2.  **Statistics & Math:** Probability, hypothesis testing (2-3 months) ➕
        3.  **Data Manipulation:** SQL and data cleaning techniques (1-2 months) 🧹
        4.  **Machine Learning:** Supervised/Unsupervised learning (3-6 months) 🤖
        5.  **Tools:** Jupyter Notebooks, scikit-learn (1 month) 🛠️
        6.  **Practice with Real Data!** (Ongoing) 📈""" # Added emojis
        return jsonify({"reply": reply})

    elif "cybersecurity" in user_message or "cyber security" in user_message or "security analyst" in user_message:
        consecutive_errors = 0
        reply = """A **Cybersecurity Analyst** protects systems and networks from digital threats. 🔒
        **Key Skills:** Networking (TCP/IP, firewalls), Operating Systems (Linux, Windows security), Cryptography, Vulnerability Assessment, Incident Response.
        **Typical Roadmap (Estimated Time):**
        1.  **Networking & OS Basics:** Understand how computers and networks work (2-3 months) 🌐
        2.  **Security Fundamentals:** Learn about common threats, defense mechanisms (2-4 months) 🛡️
        3.  **Tools:** Get hands-on with security tools (e.g., Nmap, Wireshark) (1-2 months) 🕵️‍♀️
        4.  **Ethical Hacking:** Understand attacker mindsets (for defense) (2-3 months) 😈
        5.  **Certifications:** Consider CompTIA Security+, CEH (3-6 months, varies) 📜""" # Added emojis
        return jsonify({"reply": reply})

    elif "cloud engineer" in user_message or "devops" in user_message or "devops engineer" in user_message or "cloud computing" in user_message:
        consecutive_errors = 0
        reply = """A **Cloud Engineer / DevOps Engineer** focuses on building, deploying, and managing applications in cloud environments, and automating software delivery. ☁️
        **Key Skills:** Cloud Platforms (AWS, Azure, GCP), Linux, Scripting (Python/Bash), CI/CD tools (Jenkins, GitLab CI), Containerization (Docker), Orchestration (Kubernetes), Infrastructure as Code (Terraform).
        **Typical Roadmap (Estimated Time):**
        1.  **Linux & Networking:** Strong understanding of Linux command line and network basics (2-3 months) 🐧
        2.  **Cloud Fundamentals:** Learn one major cloud provider (AWS/Azure/GCP) (3-5 months) 🚀
        3.  **Scripting:** Python or Bash for automation (1-2 months) ✍️
        4.  **CI/CD:** Understand continuous integration/delivery pipelines (2-3 months) 🔄
        5.  **Containerization:** Docker basics (1 month) 🐳
        6.  **IaC:** Learn Terraform or CloudFormation (1-2 months) 🏗️""" # Added emojis
        return jsonify({"reply": reply})

    elif "software developer" in user_message or "software engineer" in user_message or "programmer" in user_message:
        consecutive_errors = 0
        reply = """A **Software Developer/Engineer** designs, codes, tests, and maintains software applications. 💻
        **Key Skills:** Core programming language (Java, Python, C++), Data Structures & Algorithms, Object-Oriented Programming, Problem Solving, Debugging, Version Control (Git).
        **Typical Roadmap (Estimated Time):**
        1.  **Choose a Language:** Master one language (e.g., Python or Java) (2-4 months) 🧠
        2.  **DSA & OOP:** Solidify understanding of data structures, algorithms, and OOP (3-5 months) 🧩
        3.  **Development Tools:** Learn IDEs, debuggers, Git (1 month) 🛠️
        4.  **Build Small Projects:** Apply your knowledge (Ongoing) 🚀
        5.  **Testing:** Understand unit and integration testing (2-4 weeks) 🧪
        6.  **Specialization:** Decide on web, mobile, desktop, or other domains (Ongoing) ✨""" # Added emojis
        return jsonify({"reply": reply})

    elif "python developer" in user_message or "python programming" in user_message:
        consecutive_errors = 0
        reply = """A **Python Developer** specializes in building various applications, from web and data science to automation and backend systems, using the Python language. 🐍
        **Key Skills:** Python syntax, data structures, algorithms, object-oriented programming, relevant libraries (e.g., Flask/Django for web, Pandas/NumPy for data), database interaction, Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Python Fundamentals:** Syntax, variables, loops, functions, basic data structures (1-2 months) 📚
        2.  **Intermediate Python:** OOP, error handling, modules, file I/O (1-2 months) 💡
        3.  **Choose a Specialization:**
            * **Web Development:** Flask/Django (2-4 months) 🌐
            * **Data Science:** Pandas, NumPy, Matplotlib, Scikit-learn (3-6 months) 📊
            * **Automation/Scripting:** OS module, regex, web scraping (1-2 months) 🤖
        4.  **Databases:** SQL with Python (e.g., SQLAlchemy/Psycopg2) (1 month) 🗄️
        5.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        6.  **Build Projects!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "java developer" in user_message or "java programming" in user_message or \
         "c++ developer" in user_message or "c++ programming" in user_message or \
         "javascript developer" in user_message or "javascript programming" in user_message or \
         "language based developer" in user_message:
        consecutive_errors = 0
        reply = """To provide a more tailored roadmap, **which specific programming language are you interested in (e.g., Java, C++, JavaScript, C#, Go, Ruby, Swift, Kotlin, etc.)?** 🤔

        Generally, becoming a **Language-Based Developer** involves mastering a specific programming language and its ecosystem. 💻
        **Key Skills:** Chosen language syntax, core libraries/APIs, data structures, algorithms, object-oriented/functional programming (as applicable), relevant frameworks, testing, Git.
        **Typical Roadmap (Estimated Time - varies by language and specialization):**
        1.  **Language Fundamentals:** Syntax, basic constructs, data types (1-3 months) 📚
        2.  **Core Concepts:** OOP/Functional paradigms, error handling, standard library usage (2-4 months) 💡
        3.  **Ecosystem & Frameworks:** Learn popular frameworks/libraries for web, mobile, desktop, or enterprise applications in that language (3-6 months) ✨
        4.  **Databases:** How to interact with databases from your chosen language (1-2 months) 🗄️
        5.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        6.  **Build Projects!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "software tester" in user_message or "qa engineer" in user_message or "quality assurance" in user_message or "software testing" in user_message:
        consecutive_errors = 0
        reply = """A **Software Tester / QA Engineer** ensures the quality of software by identifying bugs, defects, and ensuring it meets requirements. 🧪
        **Key Skills:** Software Testing Life Cycle (STLC), Test Case Design, Bug Reporting, Manual Testing, Automation Testing (Selenium, Playwright), SQL basics, understanding of SDLC.
        **Typical Roadmap (Estimated Time):**
        1.  **Testing Fundamentals:** SDLC, STLC, types of testing (manual, automation, performance, security) (1-2 months) 📚
        2.  **Test Case Design & Execution:** Writing effective test cases, bug tracking tools (Jira, Bugzilla) (1-2 months) 📝
        3.  **SQL Basics:** For database testing (2-4 weeks) 🗄️
        4.  **Automation Testing Intro:** Learn a tool/framework (e.g., Selenium with Python/Java) (3-5 months) 🤖
        5.  **API Testing:** Tools like Postman (1 month) 🔌
        6.  **Version Control:** Git basics (2-4 weeks) 🌳
        7.  **Practice with Projects!** (Ongoing) ✅""" # Added emojis
        return jsonify({"reply": reply})

    elif "machine learning engineer" in user_message or "ml engineer" in user_message or "ai engineer" in user_message or "artificial intelligence engineer" in user_message:
        consecutive_errors = 0
        reply = """A **Machine Learning Engineer** designs, builds, and deploys AI/ML models into production systems. 🧠
        **Key Skills:** Python (NumPy, Pandas, Scikit-learn, TensorFlow/PyTorch), Linear Algebra, Calculus, Statistics, Machine Learning Algorithms, Deep Learning, MLOps, Cloud Platforms (AWS Sagemaker, Azure ML).
        **Typical Roadmap (Estimated Time):**
        1.  **Python & Data Science Basics:** Python fundamentals, Pandas, NumPy (2-3 months) 🐍
        2.  **Mathematics for ML:** Linear Algebra, Calculus, Statistics (2-4 months) ➕
        3.  **Core ML Algorithms:** Supervised, Unsupervised, Reinforcement Learning (3-6 months) 🤖
        4.  **Deep Learning:** Neural Networks, frameworks (TensorFlow/PyTorch) (3-6 months) 💡
        5.  **MLOps & Deployment:** Docker, Kubernetes, cloud ML services (2-4 months) ☁️
        6.  **Build End-to-End Projects!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "dbms" in user_message or "database architect" in user_message or "database engineer" in user_message or "database administrator" in user_message:
        consecutive_errors = 0
        reply = """A **DBMS Engineer / Database Administrator (DBA) / Database Architect** designs, implements, maintains, and optimizes databases to ensure data integrity, security, and performance. 🗄️
        **Key Skills:** SQL (Advanced), Database Management Systems (MySQL, PostgreSQL, Oracle, SQL Server), NoSQL Databases (MongoDB, Cassandra), Database Design & Modeling, Performance Tuning, Backup & Recovery, Security.
        **Typical Roadmap (Estimated Time):**
        1.  **SQL Fundamentals:** Queries, DDL, DML (1-2 months) 📝
        2.  **Relational Database Concepts:** Normalization, ACID properties (1 month) 🧩
        3.  **Specific RDBMS:** In-depth knowledge of one (e.g., MySQL or PostgreSQL) (2-4 months) 📊
        4.  **Database Design & Modeling:** ER diagrams, schema design (1-2 months) 📐
        5.  **Performance Tuning & Optimization:** Indexing, query optimization (2-3 months) ⚡
        6.  **Backup, Recovery & Security:** Strategies and implementation (1-2 months) 🔒
        7.  **NoSQL Databases (Optional but Recommended):** Basics of MongoDB, Cassandra (1-2 months) 📂
        8.  **Practice with Real-World Scenarios!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "iot developer" in user_message or "internet of things developer" in user_message:
        consecutive_errors = 0
        reply = """An **IoT Developer** specializes in building and deploying solutions for interconnected devices, focusing on hardware, software, and data communication. 🔗
        **Key Skills:** Embedded Systems (Arduino, Raspberry Pi), Programming (Python, C/C++), Networking Protocols (MQTT, HTTP), Cloud Platforms (AWS IoT, Azure IoT Hub), Data Processing, Security.
        **Typical Roadmap (Estimated Time):**
        1.  **Electronics & Microcontrollers:** Basics of circuits, Arduino/Raspberry Pi (2-3 months) 💡
        2.  **Embedded Programming:** C/C++ for microcontrollers, Python for higher-level logic (2-4 months) 💻
        3.  **Networking & Protocols:** TCP/IP, MQTT, HTTP, CoAP (1-2 months) 📡
        4.  **IoT Platforms:** Learn one cloud IoT platform (e.g., AWS IoT Core, Azure IoT Hub) (2-4 months) ☁️
        5.  **Data Handling:** Sensor data acquisition, basic data processing (1-2 months) 📊
        6.  **Security in IoT:** Understanding vulnerabilities and best practices (1 month) 🔒
        7.  **Build End-to-End IoT Projects!** (Ongoing) 🏠""" # Added emojis
        return jsonify({"reply": reply})

    elif "android developer" in user_message or "android app" in user_message or "mobile developer android" in user_message:
        consecutive_errors = 0
        reply = """An **Android Developer** builds applications for the Android operating system. 🤖
        **Key Skills:** Java or Kotlin, Android SDK, Android Studio, XML for UI layouts, Material Design, API integration, databases (SQLite/Room), Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Java or Kotlin Fundamentals:** Master one language (2-4 months) 📚
        2.  **Android Basics:** Android SDK, Android Studio IDE, basic UI components (3-5 months) 📱
        3.  **Advanced UI/UX:** Material Design, custom views (1-2 months) ✨
        4.  **Data Storage:** SQLite, Room Persistence Library (1-2 months) 🗄️
        5.  **API Integration:** Working with REST APIs (1-2 months) 🔌
        6.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        7.  **Build and Publish Apps!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "ios developer" in user_message or "ios app" in user_message or "mobile developer ios" in user_message:
        consecutive_errors = 0
        reply = """An **iOS Developer** builds applications for Apple's iOS ecosystem (iPhone, iPad). 🍎
        **Key Skills:** Swift or Objective-C, Xcode IDE, iOS SDK, SwiftUI/UIKit for UI, API integration, Core Data/Realm, Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Swift Fundamentals:** Master the Swift programming language (2-4 months) 📚
        2.  **iOS Basics:** Xcode IDE, iOS SDK, basic UI (UIKit/SwiftUI) (3-5 months) 📱
        3.  **Advanced UI/UX:** Complex layouts, animations (1-2 months) ✨
        4.  **Data Persistence:** Core Data, Realm, User Defaults (1-2 months) 🗄️
        5.  **API Integration:** Working with REST APIs (1-2 months) 🔌
        6.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        7.  **Build and Publish Apps!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "flutter developer" in user_message or "flutter programming" in user_message or "flutter app" in user_message or "cross-platform mobile developer" in user_message:
        consecutive_errors = 0
        reply = """A **Flutter Developer** builds natively compiled applications for mobile, web, and desktop from a single codebase using Google's Flutter UI toolkit. 🦋
        **Key Skills:** Dart programming language, Flutter SDK, Widget-based UI, State Management (Provider, BLoC, Riverpod), API integration, Firebase/local storage, Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Dart Fundamentals:** Master the Dart programming language (1-2 months) 📚
        2.  **Flutter Basics:** Widgets, layout, navigation, Flutter SDK (2-4 months) 📱
        3.  **State Management:** Learn a popular solution (Provider, BLoC, Riverpod) (1-2 months) 🧩
        4.  **API Integration:** Fetching data from web services (1-2 months) 🔌
        5.  **Local Data Persistence:** Shared Preferences, SQLite (1 month) 🗄️
        6.  **Firebase/Backend Integration:** Cloud Firestore, Authentication (1-2 months) ☁️
        7.  **Version Control:** Git & GitHub (2-4 weeks) 🌳
        8.  **Build and Deploy Cross-Platform Apps!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "blockchain developer" in user_message or "blockchain programming" in user_message or "crypto developer" in user_message:
        consecutive_errors = 0
        reply = """A **Blockchain Developer** designs and implements decentralized applications (DApps) and smart contracts on blockchain platforms. ⛓️
        **Key Skills:** Cryptography basics, Distributed Ledger Technology (DLT), Smart Contract Languages (e.g., Solidity for Ethereum), Blockchain Platforms (Ethereum, Hyperledger, Corda), Web3.js/Ethers.js, Token Standards (ERC-20, ERC-721), Git.
        **Typical Roadmap (Estimated Time):**
        1.  **Fundamentals:** Cryptography, Distributed Systems, Networking basics (2-3 months) 📚
        2.  **Blockchain Concepts:** Consensus mechanisms, immutability, decentralization (1-2 months) 💡
        3.  **Smart Contracts:** Learn Solidity (for Ethereum) or equivalent for other platforms (3-5 months) 📝
        4.  **Blockchain Platforms:** Dive deep into Ethereum, or explore Hyperledger, Polkadot, etc. (2-4 months) 🌐
        5.  **Web3 Development:** Interacting with blockchains from frontend apps (Web3.js/Ethers.js) (1-2 months) 🔌
        6.  **Security in Blockchain:** Common vulnerabilities, best practices (1 month) 🔒
        7.  **Build DApps and Projects!** (Ongoing) 🚀""" # Added emojis
        return jsonify({"reply": reply})

    elif "educator" in user_message or "teacher" in user_message or "professor" in user_message or "lecturer" in user_message or "computer instructor" in user_message:
        consecutive_errors = 0
        reply = """An **Educator / Teacher** in the computer science or IT field shares knowledge and guides students in academic or vocational settings. 🧑‍🏫
        **Key Skills:** Strong subject matter expertise (Computer Science, programming, IT concepts), excellent communication, presentation skills, patience, curriculum development, classroom management (if applicable).
        **Typical Roadmap (Estimated Time):**
        1.  **Strong BCA Foundation:** Master core computer science concepts (Ongoing throughout BCA) 🎓
        2.  **Further Education:** MCA, M.Sc. in CS/IT, or B.Ed. (for school-level teaching) (2-3 years) 📚
        3.  **Communication & Presentation Skills:** Practice explaining complex topics clearly (Ongoing) 🗣️
        4.  **Pedagogy Basics:** Understand teaching methodologies (can be self-taught or through B.Ed.) (1-3 months) 💡
        5.  **Practical Experience:** Internships, tutoring, teaching assistant roles (Ongoing) 🤝
        6.  **Specialization:** Focus on specific subjects you want to teach (e.g., Python, Web Dev, Data Science) (Ongoing) ✨""" # Added emojis
        return jsonify({"reply": reply})

    consecutive_errors += 1
    if consecutive_errors >= 2:
        reply = "I'm sorry, I can only provide guidance for specific tech career paths like Web Developer, Data Scientist, Cybersecurity, Cloud/DevOps, Software Developer, Python Developer, Software Tester, Machine Learning Engineer, Database roles, IoT Developer, Android Developer, iOS Developer, Blockchain Developer, Educator, or Flutter Developer. You might find more general help by trying a broader AI like Google Gemini: [https://gemini.google.com/](https://gemini.google.com/) 🤖" # Added emoji
        consecutive_errors = 0
    else:
        reply = "Sorry, I couldn't understand your request. Can you please ask again, perhaps by mentioning a specific tech career or skill? 🤔" # Added emoji
    
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)
