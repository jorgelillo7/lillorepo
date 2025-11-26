# Gemini Configuration for Lillorepo

This document provides a summary of the `lillorepo` monorepo for the Gemini AI agent.

## Repository Overview

`lillorepo` is a Bazel-based monorepo containing various projects primarily focused on tools and analytics for the Biwenger fantasy football platform.

### Key Technologies
- **Build System:** Bazel
- **Primary Language:** Python
- **Key Libraries:** Flask, Selenium, Google Cloud SDK

### Directory Structure

-   `📁 /core`: Shared libraries and utilities.
    -   `sdk/`: API clients for Biwenger, GCP, and Telegram.
    -   `utils.py`: Common utility functions.
-   `📁 /packages`: Individual, self-contained projects.
    -   `biwenger_tools/`: A collection of agents and tools for Biwenger.
        -   `scraper_job/`: A job to scrape messages from the Biwenger league board.
        -   `teams_analyzer/`: An agent to analyze Biwenger teams and generate reports.
        -   `web/`: A Flask-based web application to display scraped data.
-   `📁 /docker`: Docker configurations.
-   `📁 /docs`: Project documentation.
-   `📁 /scripts`: Utility scripts.
-   `📁 /tools`: Bazel build tools and extensions.

## Main Projects

1.  **Scraper Job (`/packages/biwenger_tools/scraper_job`)**: An automated scraper that fetches board messages from a Biwenger league, processes them into CSV files, and syncs them to Google Drive.
2.  **Teams Analyzer (`/packages/biwenger_tools/teams_analyzer`)**: Analyzes Biwenger league teams by fetching data from the Biwenger API and enriching it with data from external fantasy football websites. It generates a detailed CSV report and can send it to a Telegram chat.
3.  **Web App (`/packages/biwenger_tools/web`)**: A Flask web application that visualizes the data collected by the scraper job. It is deployed on Google Cloud Run.

For more detailed information on the agents, please refer to [AGENTS.md](../AGENTS.md).
