from abc import ABC, abstractmethod

from openai import AsyncOpenAI, AsyncAzureOpenAI
from browser_use import ChatOpenAI, ChatAzureOpenAI
from browser_use.llm.base import BaseChatModel

class ModelConfiguration(ABC):

    def __init__(self, base_url: str, model: str, api_key: str, api_version: str | None = None):    
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.api_version = api_version

    @abstractmethod
    def connect_generic_llm(self) -> AsyncOpenAI:
        """
        Provides LLM connection using generic API (OpenAI, Azure, ...)
        """
        
    @abstractmethod
    def connect_browser_llm(self) -> BaseChatModel:
        """
        Provides LLM connection using a browser-use API
        """

class OpenAIModelConfiguration(ModelConfiguration):
    def __init__(self, base_url: str, model: str, api_key: str):
        super().__init__(base_url, model, api_key)
    
    
    def connect_generic_llm(self) -> AsyncOpenAI:
        """
        Provides LLM connection using generic API (OpenAI, Azure, ...)
        """
        return AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=180,
        )
        
    def connect_browser_llm(self) -> ChatOpenAI:
        """
        Provides LLM connection using a browser-use API
        """
        return ChatOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
        )

class AzureModelConfiguration(ModelConfiguration):
    def __init__(self,  model: str, api_key: str, base_url: str, api_version: str):
        super().__init__(base_url=base_url, model=model, api_key=api_key, api_version=api_version)

    def connect_generic_llm(self) -> AsyncAzureOpenAI:
        """
        Provides LLM connection using generic API (OpenAI, Azure, ...)
        """
        return AsyncAzureOpenAI(
            azure_endpoint=self.base_url,
            api_key=self.api_key,
            api_version=self.api_version,
            timeout=180,
        )
        
    def connect_browser_llm(self) -> ChatAzureOpenAI:
        """
        Provides LLM connection using a browser-use API
        """
        return ChatAzureOpenAI(
            azure_endpoint=self.base_url,
            model=self.model,
            api_key=self.api_key,
            api_version=self.api_version,
        )





