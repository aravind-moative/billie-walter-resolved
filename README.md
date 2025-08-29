# Billie - Davidson Water, Inc. AI Chatbot

Billie is an intelligent customer service chatbot for Davidson Water, Inc., designed to handle customer inquiries about outages, billing, meter readings, and utility services. The application features a conversational AI agent built with LangGraph and provides a comprehensive dashboard for monitoring utility status. This project is built with Flask, LangChain, and Tailwind CSS.

## Features

### Core Functionality
- **Outage Management**: Report and check status of utility outages (Power, Water, Gas, Internet)
- **Billing Information**: Access account balances, payment history, and due dates
- **Meter Readings**: View current and historical meter data
- **Usage Analysis**: Analyze consumption patterns and bill changes
- **Paperless Billing**: Enroll customers in paperless billing services

### Interaction Channels
- **Web Chat Interface**: Modern, responsive chat UI with phone number verification
- **Voice Calls**: Twilio-powered voice interactions with text-to-speech
- **SMS Integration**: Text message support via Twilio
- **Bland AI Integration**: Third-party chatbot platform support

### Administrative Features
- **Admin Dashboard**: Comprehensive view of outages, customers, and billing data
- **User Management**: Admin user creation and authentication
- **Data Management**: CRUD operations for outages and customer accounts

## Architecture

### Technology Stack
- **Backend**: Flask (Python 3.11+)
- **Database**: SQLite with SQLAlchemy ORM
- **AI/ML**: LangGraph, LangChain, OpenAI GPT-4
- **Text-to-Speech**: ElevenLabs API
- **Voice/SMS**: Twilio API
- **Frontend**: HTML/CSS/JavaScript with Tailwind CSS
- **Package Management**: uv (Python), npm (Node.js)

### Project Structure
```
Billie/
├── app/                          # Main application code
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Configuration settings
│   ├── models.py                # SQLAlchemy database models
│   ├── routes/                  # Flask route handlers
│   │   ├── api.py              # REST API endpoints
│   │   ├── auth.py             # Authentication routes
│   │   ├── bland.py            # Bland AI webhook
│   │   ├── twilio_phone.py     # Voice call handling
│   │   ├── twilio_sms.py       # SMS handling
│   │   └── web.py              # Web interface routes
│   ├── utilities/               # Utility modules
│   │   ├── admin_management.py # Admin user management
│   │   ├── database.py         # Database operations
│   │   ├── instances.py        # Flask app instances
│   │   └── text_to_speech.py   # TTS functionality
│   └── utility_agent_langgraph.py # Main AI agent logic
├── templates/                   # HTML templates
├── static/                      # Static assets (CSS, JS, images)
├── databases/                   # SQLite database files
├── run.py                       # Application entry point
├── db_setup.sql                # Database schema and sample data
└── pyproject.toml              # Python dependencies
```

## Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Node.js (for Tailwind CSS compilation)
- uv package manager

### 1. Clone and Setup Environment
```bash
# Clone the repository
git clone <repository-url>
cd Billie

# Create virtual environment and install dependencies
uv sync

# Update dependencies (recommended)
uv lock --upgrade
uv sync
```

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
# AI Model Configuration
GEMINI_API_KEY=your-gemini-api-key
GEMINI_FLASH_MODEL_NAME=gemini-2.0-flash
GEMINI_TEMPERATURE=1.0

OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL_NAME=gpt-4.1

# LangSmith Configuration
LANGSMITH_TRACING=your-langsmith-tracing
LANGSMITH_ENDPOINT=your-langsmith-endpoint
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=your-langsmith-project

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key

# API Keys
ELEVENLABS_API_KEY=your-elevenlabs-api-key

# Twilio Configuration
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token

# Base URL (required for audio file serving)
BASE_URL=https://billie.moative.com  # or your ngrok URL
```

### 3. Database Setup
```bash
# Initialize the database with sample data
sqlite3 app/databases/myusage.db < db_setup.sql
```

### 4. Admin User Creation
```bash
# Create an admin user
python app/utilities/admin_management.py create \
  --email "admin@example.com" \
  --password "your-password" \
  --name "Admin Name"
```

### 5. Frontend Assets
```bash
# Install Node.js dependencies
npm install

# Build Tailwind CSS (development with watch)
npm run build
```

### 6. Run the Application
```bash
# Development mode
python run.py

# Production mode (with gunicorn)
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

The application will be available at `http://localhost:8000`

## Configuration

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Flask environment | `development` |
| `FLASK_DEBUG` | Debug mode | `False` |
| `SECRET_KEY` | Flask secret key | Required |
| `BASE_URL` | Application base URL | `https://billie.moative.com` |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL_NAME` | OpenAI model name | `gpt-4.1` |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Required |

### Database Configuration
The application uses SQLite databases stored in `app/databases/`:
- `myusage.db`: Main application database
- `admin.db`: Admin user database
- `utility_agent_memory.db`: LangGraph conversation memory

## AI Agent Architecture

### LangGraph Implementation
The AI agent is built using LangGraph with the following components:

1. **State Management**: Conversation state with message history
2. **Tool Integration**: Custom tools for utility operations
3. **Memory Persistence**: SQLite-based conversation memory
4. **Customer Context**: Phone number-based customer identification

### Available Tools
- `report_outage()`: Report new utility outages
- `check_outage_status()`: Check existing outage status
- `get_account_balance()`: Retrieve account balance
- `get_meter_reading()`: Get meter reading data
- `get_bill_balance()`: Access billing information
- `get_payment_link()`: Generate payment links
- `analyze_usage_patterns()`: Analyze consumption patterns
- `enroll_paperless_billing()`: Enroll in paperless billing

### Conversation Flow
1. Customer verification via phone number
2. Intent recognition and tool selection
3. Database operations and data retrieval
4. Natural language response generation
5. Context preservation for follow-up interactions

## User Interfaces

### Web Chat Interface
- **Phone Number Verification**: Required for customer identification
- **Real-time Chat**: WebSocket-like experience with session persistence
- **Voice Mode**: Audio input/output capabilities
- **Dark Mode**: Toggle between light and dark themes
- **Mobile Responsive**: Optimized for all device sizes

### Admin Dashboard
- **Outage Management**: View and manage reported outages
- **Customer Data**: Access customer accounts and billing information
- **Meter Readings**: Monitor meter data and usage patterns
- **Data Export**: Comprehensive data tables with filtering

### Voice Interface
- **Twilio Integration**: Phone call handling with speech recognition
- **Text-to-Speech**: ElevenLabs-powered natural voice responses
- **Call Logging**: Automatic call recording and analytics

## API Endpoints

### Authentication
- `POST /login` - Admin login
- `GET /logout` - Admin logout

### Chat API
- `POST /api/chat` - Process chat messages
- `POST /api/transcribe` - Audio transcription
- `POST /api/clear-data` - Clear conversation history
- `GET /api/audio/<filename>` - Serve generated audio files

### Management API
- `DELETE /api/delete-outage/<reference_number>` - Delete outage
- `DELETE /api/delete-account/<account_id>` - Delete customer account
- `DELETE /api/delete-admin/<email>` - Delete admin user

### External Integrations
- `POST /phone` - Twilio voice webhook
- `POST /gather` - Twilio speech gathering
- `POST /sms` - Twilio SMS webhook
- `POST /webhook/bland` - Bland AI webhook

## Database Schema

### Core Tables
- **accounts**: Customer account information
- **billing_info**: Billing and payment data
- **meters**: Meter information and configurations
- **readings**: Meter reading history
- **summaries**: Usage summaries and analytics
- **outages**: Outage reports and status

### Admin Tables
- **admin_users**: Admin user accounts and authentication


## Testing

### Manual Testing
1. **Web Chat**: Test customer interactions via web interface
2. **Voice Calls**: Verify Twilio voice integration
3. **SMS**: Test SMS functionality
4. **Admin Dashboard**: Validate administrative functions

### API Testing
Use tools like Postman or curl to test API endpoints:
```bash
# Test chat API
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What's my account balance?", "phone_number": "7550026048"}'
```


## Contributing

### Development Workflow
1. Create feature branch from main
2. Implement changes with proper testing
3. Update documentation as needed
4. Submit pull request with detailed description

### Code Standards
- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Maintain comprehensive docstrings
- Run linting with ruff before committing
