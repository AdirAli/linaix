from typing import Optional

import os


class ProviderError(Exception):
    pass

#Call the Google Gemini API to generate text
def generate_with_google(api_key: str, model_name: str, prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0),
            )
        finally:
            try:
                client.close()
            except Exception:
                pass
        #Extract textform response
        text = getattr(resp, "text", None)
        if not text:
            raise ProviderError("Google provider returned no text")
        return text
    except Exception as exc:
        raise ProviderError(f"Google provider failed: {exc}")

#Call the OpenAI API to generate text
def generate_with_openai(api_key: str, model_name: str, prompt: str) -> str:
    try:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.responses.create(model=model_name, input=prompt)
            text = getattr(resp, "output_text", None)
            if not text:
                try:
                    text = "".join([b.text for b in resp.output[0].content if getattr(b, "text", None)])
                except Exception:
                    pass
            if not text:
                raise ProviderError("OpenAI provider returned no text")
            return text
        except ImportError:
            import openai  # legacy
            openai.api_key = api_key
            completion = openai.ChatCompletion.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            text = completion["choices"][0]["message"]["content"].strip()
            if not text:
                raise ProviderError("OpenAI legacy provider returned empty text")
            return text
    except Exception as exc:
        raise ProviderError(f"OpenAI provider failed: {exc}")

#accept various names for providers
def normalize_provider_name(name: Optional[str]) -> str:
    name = (name or "").strip().lower()
    if name in {"google", "gemini", "g", "gg"}:
        return "google"
    if name in {"openai", "chatgpt", "oai", "gpt"}:
        return "openai"
    return "google"
