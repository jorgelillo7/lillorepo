# Configuring the Agent

This document outlines how you can configure the agent's behavior, set operational modes, and customize its responses to better suit your needs.

## Setting Operational Modes

While the agent does not have a hardcoded "reasoning mode 3.0," you can dynamically shape its behavior by providing clear, upfront instructions. You can think of this as setting a "persona" or "mode" for the duration of a task.

By defining a set of principles at the beginning of a conversation, you can guide the agent’s focus, tone, and decision-making process.

### Example: Setting a "Secure Coder" Mode

You can instruct the agent to act with a specific focus. For example:

> "For this session, act as a senior security engineer. Prioritize code security, validate all inputs, and explain potential vulnerabilities in any code we write or review."

## Conceptual Configuration Commands

Although the Gemini CLI does not have a built-in `config` command for the agent, we can define a conceptual framework for what such a system might look like. The following commands are examples of how you could imagine configuring the agent's model and behavior.

### Model Selection

This command would theoretically allow you to switch the underlying model that the agent uses and view the currently active one.

```bash
# Sets the agent to use a specific reasoning model (e.g., a more advanced model).
gemini config set model gemini-3.0-pro

# Sets the agent to use a faster, more cost-effective model (e.g., a "flash" model).
gemini config set model gemini-2.5-flash-image

# Views the currently active model configuration.
gemini config get model
```

### Other Examples

Here are other potential configuration settings that could be useful:

- **Verbosity Level:** Control how concise or detailed the agent's explanations are.
  ```bash
  # Options: low, medium, high
  gemini config set verbosity low
  ```

- **Execution Strategy:** Tell the agent to be more cautious or more autonomous.
  ```bash
  # Options: cautious (ask for confirmation on every step), autonomous (proceed with confidence)
  gemini config set strategy cautious
  ```

- **Coding Style:** Inform the agent to adhere to a specific style guide.
  ```bash
  # Options: pep8, google, standardjs, etc.
  gemini config set coding_style pep8
  ```

## Gemini CLI Environment Variables

To configure the Gemini CLI, you typically set environment variables that control its behavior, authentication, and access to models. These variables are read by the CLI at runtime.

### Common Environment Variables

-   **`GEMINI_API_KEY`**: Your API key for authenticating with the Gemini API. This is crucial for accessing the models.
-   **`GEMINI_MODEL`**: Specifies the default Gemini model to use (e.g., `gemini-pro`, `gemini-2.5-flash-image`).
-   **`GEMINI_TEMP_DIR`**: (Conceptual) Sets a custom temporary directory for the CLI's operations.

### How to Set Environment Variables

You can set these variables in your shell profile (e.g., `.bashrc`, `.zshrc`) or directly in your current terminal session:

```bash
# Example: Setting the Gemini API Key
export GEMINI_API_KEY="your_api_key_here"

# Example: Setting a default model
export GEMINI_MODEL="gemini-2.5-flash-image"
```

**Note:** Always keep your API keys secure and avoid committing them to version control.
