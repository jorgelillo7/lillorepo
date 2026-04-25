# ⚽ Biwenger Teams Analyser

A set of Python tools that extract, analyse, and report data from your Biwenger league. It uses the Biwenger API and scrapes sites like "Analítica Fantasy" and "Jornada Perfecta" to enrich the data.

Dual objective:
1. Generate a **CSV** file with a comprehensive analysis of your league.
2. Automatically send that analysis to your **Telegram chat**.

## 🚀 Key Features

* **Full Analysis**:
- **`squads_export.csv`**: Main report with all players, their value, clause, and extracted analysis data.

- **`analitica_fantasy_data_backup.csv`**: Raw backup file with data scraped from "Analítica Fantasy". Useful for verifying the scraping worked correctly.

* **Telegram notifications**: Automatically sends the generated file to a Telegram chat (if environment variables are configured).

## ⚙️ Configuration and Usage

For detailed setup instructions, see the main operations document.

* **Installation and dependencies**: See section **`1.3 Teams Analyzer`** in `operations.md`.
* **Credentials setup**: Biwenger and Telegram variables are set in the `.env` file.
* **Running**: The local execution command is in `operations.md`.

---

### **How to get Telegram credentials**

If you want notifications, you need a **bot token** and a **chat ID**.

1. **Create a Bot**: Talk to `@BotFather` on Telegram. Use the `/newbot` command, give it a name, and it will provide your `TELEGRAM_BOT_TOKEN`.
2. **Get your Chat ID**: Use the bot token in the following URL (replacing the brackets) to get your chat ID.

    `https://api.telegram.org/bot[TELEGRAM_BOT_TOKEN]/getUpdates`

    The response JSON will show your chat ID.

---

### **🔧 Customisation and Maintenance**

#### **Player Name Mappings**

Sometimes a player's name in Biwenger does not exactly match the name on analysis sites. To fix this, add exceptions to the `PLAYER_NAME_MAPPINGS` dictionary at the top of the script.

**Example:**
```python
PLAYER_NAME_MAPPINGS = {
    'odysseas': 'vlachodimos',
    'carlos vicente': 'c. vicente',
}
```

## ⚠️ Important Notes

- **Headless mode**: To run the script faster without opening a browser window, enable headless mode in the `fetch_analitica_fantasy_coeffs` function by uncommenting the `# chrome_options.add_argument("--headless")` line.
