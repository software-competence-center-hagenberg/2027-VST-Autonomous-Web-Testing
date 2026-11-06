import asyncio
from agents.browser_manager import BrowserManager
from typing import Any

from abc import ABC, abstractmethod

class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> Any:
        pass

class GetCurrentURLTool(Tool):
    name = "get_current_url"
    description = "Returns the current URL from the browser."
    parameters = {}  # no arguments needed

    def __init__(self, browser_manager:BrowserManager):
        self.browser_manager = browser_manager

    async def run(self, arguments: dict[str, Any]) -> str:
        return await self.browser_manager.get_URL()
    
class DomContainsTextTool(Tool):
    name = "dom_contains_text"
    description = "Checks whether the page text contains a given string."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> bool | str:
        page = await self.browser_manager.browser.must_get_current_page()
        text = arguments.get("text")
        if not text:
            return "[Error] DomContainsTextTool: missing required argument 'text'"

        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    "(t) => { try { return document.body.innerText.includes(t); } catch(e) { return 'Error: ' + e.message; } }",
                    text,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] DomContainsTextTool failed with text '{text}': {result}")
                return f"[Error] DomContainsTextTool failed with text '{text}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating text '{text}' took too long.")
            return False
        except Exception as e:
            print(f"[Error] Failed to evaluate text '{text}': {e}")
            return False

class DomExistsSelectorTool(Tool):
    name = "dom_exists_selector"
    description = "Checks whether a CSS selector exists on the page."
    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
        },
        "required": ["selector"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> bool | str:
        page = await self.browser_manager.browser.must_get_current_page()
        selector = arguments.get("selector")
        if not selector:
            return "[Error] DomExistsSelectorTool: missing required argument 'selector'"

        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    "(sel) => { try { return document.querySelector(sel) !== null; } catch(e) { return 'Error: ' + e.message; } }",
                    selector,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] DomExistsSelectorTool Failed with selector '{selector}': {result}")
                return f"[Error] DomExistsSelectorTool Failed with selector '{selector}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating selector '{selector}' took too long.")
            return False
        except Exception as e:
            print(f"[Error] DomExistsSelectorTool Failed with selector '{selector}': {e}")
            return False

class DomCountSelectorTool(Tool):
    name = "dom_count_selector"
    description = "Counts how many elements match a CSS selector."
    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
        },
        "required": ["selector"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> int | str:
        page = await self.browser_manager.browser.must_get_current_page()
        selector = arguments.get("selector")
        if not selector:
            return "[Error] DomCountSelectorTool: missing required argument 'selector'"

        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    "(sel) => { try { return document.querySelectorAll(sel).length; } catch(e) { return 'Error: ' + e.message; } }",
                    selector,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] DomCountSelectorTool Failed with selector '{selector}': {result}")
                return f"[Error] DomCountSelectorTool Failed with selector '{selector}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating selector '{selector}' took too long.")
            return -1
        except Exception as e:
            print(f"[Error] DomCountSelectorTool Failed with selector '{selector}': {e}")
            return -1

class DomGetTextTool(Tool):
    name = "dom_get_text"
    description = "Returns the inner text of the first element matching a selector."
    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
        },
        "required": ["selector"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> str :
        page = await self.browser_manager.browser.must_get_current_page()
        selector = arguments.get("selector")
        if not selector:
            return "[Error] DomGetTextTool: missing required argument 'selector'"

        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    """(sel) => {
                        try {
                            const el = document.querySelector(sel);
                            return el ? el.innerText : null;
                        } catch(e) { return 'Error: ' + e.message; }
                    }""",
                    selector,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] DomGetTextTool Failed with selector '{selector}': {result}")
                return f"[Error] DomGetTextTool Failed with selector '{selector}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating selector '{selector}' took too long.")
            return [f"[Timeout] Evaluating selector '{selector}' took too long."]
        except Exception as e:
            print(f"[Error] DomGetTextTool Failed with selector '{selector}': {e}")
            return [f"[Error] DomGetTextTool Failed with selector '{selector}': {e}"]


class FindElementsByIdTool(Tool):
    name = "find_elements_by_id"
    description = "Returns a list of inner texts of elements matching a given HTML id."
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
        },
        "required": ["id"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> list[str] | str:
        page = await self.browser_manager.browser.must_get_current_page()
        element_id = arguments.get("id")
        if not element_id:
            return "[Error] FindElementsByIdTool: missing required argument 'id'"

        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    """(id) => {
                        try {
                            const elements = document.querySelectorAll(`#${id}`);
                            return Array.from(elements).map(el => el.innerText);
                        } catch(e) { return 'Error: ' + e.message; }
                    }""",
                    element_id,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] FindElementsByIdTool failed with id '{element_id}': {result}")
                return f"[Error] FindElementsByIdTool failed with id '{element_id}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating element_id '{element_id}' took too long.")
            return ["Function failed with Timeout"]
        except Exception as e:
            print(f"[Error] Failed to evaluate element_id '{element_id}': {e}")
            return [f"Function failed to evaluate element_id '{element_id}': {e}"]

class FindElementsByIdHTMLTool(Tool):
    name = "find_elements_by_id_html"
    description = "Returns a list of outerHTML strings of elements matching a given HTML id."
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
        },
        "required": ["id"],
    }

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> list[str] | str:
        page = await self.browser_manager.browser.must_get_current_page()
        element_id = arguments.get("id")
        if not element_id:
            return "[Error] FindElementsByIdHTMLTool: missing required argument 'id'"
        
        try:
            result = await asyncio.wait_for(
                page.evaluate(
                    """(id) => {
                        try {
                            const elements = document.querySelectorAll(`#${id}`);
                            return Array.from(elements).map(el => el.outerHTML);
                        } catch(e) { return 'Error: ' + e.message; }
                    }""",
                    element_id,
                ),
                timeout=self.timeout
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"[Error] FindElementsByIdHTMLTool failed with id '{element_id}': {result}")
                return f"[Error] FindElementsByIdHTMLTool failed with id '{element_id}': {result}"
            return result
        except asyncio.TimeoutError:
            print(f"[Timeout] Evaluating element_id '{element_id}' took too long.")
            return ["Function failed with Timeout"]
        except Exception as e:
            print(f"[Error] Failed to evaluate element_id '{element_id}': {e}")
            return [f"Function failed to evaluate element_id '{element_id}': {e}"]

class GetAllIdsTool(Tool):
    name = "get_all_ids"
    description = "Returns a list of all element IDs found on the page."
    parameters = {}  # no arguments needed

    def __init__(self, browser_manager: BrowserManager, timeout: float = 5.0):
        self.browser_manager = browser_manager
        self.timeout = timeout

    async def run(self, arguments: dict[str, Any]) -> list[str]:
        page = await self.browser_manager.browser.must_get_current_page()

        try:
            return await asyncio.wait_for(
                page.evaluate(
                    """() => {
                        const elements = document.querySelectorAll('[id]');
                        return Array.from(elements).map(el => el.id);
                    }"""
                ),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            print("[Timeout] Getting all IDs took too long.")
            return ["Function failed with Timeout"]
        except Exception as e:
            print(f"[Error] Failed to get all IDs: {e}")
            return [f"Function failed to get all IDs: {e}"]
