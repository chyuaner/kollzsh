#!/usr/bin/env python3
import json
import logging
import os
import re
import sys

from ollama import Client

# Configure logging
LOG_FILE = "/tmp/kollzsh_debug.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def log_debug(message, data=None):
    """Log debug message with optional data."""
    if data:
        logging.debug(f"{message}\nData: {data}\n----------------------------------------")
    else:
        logging.debug(message)


def get_shell_command_tool(commands: list[str]) -> dict:
    """
    Generate shell command tool specification for Ollama

    Args:
        commands: List of shell commands to be executed

    Returns:
        dict: Tool specification containing name, description, and parameters
    """
    log_debug("Generating tool specification for commands:", commands)
    return commands


def interact_with_ollama(user_query):
    """Interact with the Ollama server and retrieve command suggestions."""
    api_key = os.getenv("KOLLZSH_APIKEY", "")
    if api_key:
        client = Client(host=os.environ["KOLLZSH_URL"], headers={'Authorization': 'Bearer ' + api_key})
    else:
        client = Client(host=os.environ["KOLLZSH_URL"])

    log_debug("Sending query to Ollama:", user_query)

    # Format the user query to focus on shell commands
    formatted_query = (
        f"Generate shell commands for the following task: {user_query}. \n"
        "Provide multiple relevant commands if available. \n"
        "Output in JSON format with markdown-wrapped JSON. \n"
        "The JSON needs to include a key named 'commands' with a list of commands. \n"
    )

    try:
        response = client.chat(
            model=os.environ["KOLLZSH_MODEL"],
            keep_alive=os.environ["KOLLZSH_KEEP_ALIVE"],
            messages=[{"role": "user", "content": formatted_query}],
            stream=False,
            tools=[get_shell_command_tool],
        )
        log_debug("Received response from Ollama:", response)

        # Extract tool calls from the response
        if hasattr(response.message, "tool_calls") and response.message.tool_calls:
            for tool_call in response.message.tool_calls:
                if tool_call.function.name == "get_shell_command_tool":
                    try:
                        commands = tool_call.function.arguments.get("commands", [])
                        if commands:
                            log_debug("Successfully extracted commands:", commands)
                            return commands
                    except AttributeError as e:
                        log_debug(f"Error accessing tool call arguments: {str(e)}")

        # Fallback to parsing content if no tool calls
        content = response.message.content if hasattr(response.message, "content") else ""
        if content:
            log_debug("No tool calls found, falling back to content parsing")
            return parse_commands(content)

        log_debug("No valid commands found in response")
        return []

    except Exception as e:
        log_debug(f"Error interacting with Ollama: {str(e)}")
        return []


def parse_commands(content):
    """Parse commands from response content."""
    try:
        # Try to find markdown-wrapped JSON first
        markdown_match = re.search(r"```(json|bash|zsh)\s*(.*?)\s*```", content, re.DOTALL)
        if markdown_match:
            content_type = markdown_match.group(1)
            content = markdown_match.group(2)
        else:
            content_type = None

        # Clean and normalize the content
        content = normalize_json_string(content)
        log_debug("Normalized content:", content)

        # Try parsing as JSON
        if not content_type or content_type == "json":
            try:
                commands = json.loads(content)
            except json.JSONDecodeError:
                log_debug("Content is not a valid JSON object")

        # Try parsing as shell commands
        if not content_type or content_type == "bash" or content_type == "zsh":
            commands = content.split("\n")

        # Ensure we have a list of commands
        if isinstance(commands, list):
            # Clean up commands
            cleaned_commands = []
            for cmd in commands:
                if isinstance(cmd, str):
                    # Clean up escaping but preserve shell escapes
                    cmd = cmd.replace('\\"', '"')  # Unescape quotes
                    cmd = cmd.replace("\\\\", "\\")  # Fix double escapes
                    cmd = cmd.replace('"', '\\"')  # Re-escape quotes for shell
                    cleaned_commands.append(cmd)

            log_debug("Successfully parsed commands:", cleaned_commands)
            return cleaned_commands

        log_debug("Parsed content is not a list:", commands)
        return content

    except Exception as e:
        log_debug(f"Error parsing commands: {str(e)}", content)
        return content


def normalize_json_string(content):
    """Normalize JSON string by handling escapes and newlines."""
    # Handle control characters
    content = content.replace("\n", " ")
    content = content.replace("\r", " ")
    content = content.replace("\t", " ")

    # Handle escaped characters
    content = content.replace('\\"', '"')  # Temporarily unescape quotes
    content = content.replace("\\\\", "\\")  # Fix double escapes
    content = content.replace('"', '\\"')  # Re-escape all quotes

    # Clean up whitespace
    content = " ".join(content.split())

    log_debug("Normalized JSON string:", content)
    return content


if __name__ == "__main__":
    if len(sys.argv) != 2:
        log_debug("Usage: ollama_util.py <user_query>")
        sys.exit(1)

    user_query = sys.argv[1]
    commands = interact_with_ollama(user_query)

    if not commands:
        log_debug("No valid commands found")
        sys.exit(1)

    # Print each command on a new line
    for cmd in commands:
        print(cmd)

    log_debug("Successfully output commands")
