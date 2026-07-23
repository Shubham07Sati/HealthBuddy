import json
import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential
import instructor
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
import google.generativeai as genai

from app.core.config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)

class LLMProvider:
    def __init__(self):
        self.provider = settings.llm_provider
        
        if self.provider == "openai" and settings.openai_api_key:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.client = instructor.patch(self._openai_client, mode=instructor.Mode.TOOLS)
            self.default_model = settings.openai_model or "gpt-4o"
        elif self.provider == "anthropic" and settings.anthropic_api_key:
            self._anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self.client = instructor.patch(self._anthropic_client, mode=instructor.Mode.ANTHROPIC_TOOLS)
            self.default_model = settings.generator_model or "claude-3-5-sonnet-20240620"
        elif self.provider == "google" and settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)
            self.default_model = settings.google_model or "gemini-1.5-pro"
            # note: instructor for gemini is usually via VertexAI or OpenAI compatibility layer,
            # this scaffold uses a direct call wrapper for structured output
        elif self.provider == "ollama" and settings.ollama_base_url:
            self._openai_client = AsyncOpenAI(
                base_url=f"{settings.ollama_base_url}/v1", 
                api_key="ollama"
            )
            self.client = instructor.patch(self._openai_client, mode=instructor.Mode.JSON)
            self.default_model = settings.ollama_model or "llama3"
        else:
            log.warning("No valid LLM provider configuration found.")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_structured_completion(
        self, 
        messages: List[Dict[str, str]], 
        response_model: Type[BaseModel], 
        model: Optional[str] = None
    ) -> BaseModel:
        """Get structured Pydantic output from the configured LLM"""
        
        target_model = model or self.default_model
        
        try:
            if self.provider in ["openai", "anthropic", "ollama"]:
                response = await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    response_model=response_model,
                    max_tokens=4096,
                )
                return response
            elif self.provider == "google":
                # Fallback for Gemini without instructor (requires custom parsing or wait for native support)
                gemini_model = genai.GenerativeModel(target_model)
                prompt = f"Convert the following request into JSON matching this schema: {response_model.model_json_schema()}\n\n"
                prompt += json.dumps(messages)
                
                resp = await gemini_model.generate_content_async(
                    prompt, 
                    generation_config=genai.GenerationConfig(response_mime_type="application/json")
                )
                return response_model.model_validate_json(resp.text)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
                
        except Exception as e:
            log.error(f"LLM Error: {str(e)}")
            raise

llm = LLMProvider()
