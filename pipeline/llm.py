from typing import Any, Dict, Optional, Tuple
from openai import AsyncOpenAI, OpenAI

_CLIENT_CACHE: Dict[Tuple[str, str], OpenAI] = {}
_ASYNC_CLIENT_CACHE: Dict[Tuple[str, str], AsyncOpenAI] = {}


def _get_client(api_key: str, base_url: str, timeout: float) -> OpenAI:
    key = (str(base_url or ""), str(api_key or ""))
    client = _CLIENT_CACHE.get(key)
    if client is None:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        _CLIENT_CACHE[key] = client
    return client


def _get_async_client(api_key: str, base_url: str, timeout: float) -> AsyncOpenAI:
    key = (str(base_url or ""), str(api_key or ""))
    client = _ASYNC_CLIENT_CACHE.get(key)
    if client is None:
        client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        _ASYNC_CLIENT_CACHE[key] = client
    return client


def openai_interface(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    top_k: Optional[int] = None,
    enable_thinking: bool = False,
    stream: bool = True,
    timeout: float = 60.0,
):
    client = _get_client(api_key=api_key, base_url=base_url, timeout=timeout)

    extra_body = {
        "enable_thinking": enable_thinking,
        "chat_template_kwargs": {
            "thinking": enable_thinking,
            "enable_thinking": enable_thinking,
        },
    }
    if top_k is not None:
        extra_body["top_k"] = top_k

    create_kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        extra_body=extra_body,
        timeout=timeout,
    )

    if not stream:
        response = client.chat.completions.create(**create_kwargs)
        msg = response.choices[0].message if response.choices else None
        reasoning_content = ""
        content = ""
        if msg:
            reasoning_content = (
                getattr(msg, "reasoning", None)
                or getattr(msg, "reasoning_content", None)
                or ""
            )
            content = getattr(msg, "content", None) or ""
        usage_info = getattr(response, "usage", None)
        return reasoning_content, content, usage_info

    response = client.chat.completions.create(
        **create_kwargs,
        stream=True,
        stream_options={"include_usage": True},
    )

    # 初始化流式收集变量
    reasoning_content = ""
    content = ""
    reasoning_started = False
    content_started = False
    usage_info = None

    # 处理流式响应
    for chunk in response:
        if chunk.usage:
            usage_info = chunk.usage

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        # 流式推理过程输出
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if not reasoning_started and delta.reasoning_content.strip():
                reasoning_started = True
            reasoning_content += delta.reasoning_content

        # 流式回答内容输出
        if hasattr(delta, "content") and delta.content:
            if not content_started and delta.content.strip():
                content_started = True
            content += delta.content

    return reasoning_content, content, usage_info


async def async_openai_interface(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    top_k: Optional[int] = None,
    enable_thinking: bool = False,
    stream: bool = True,
    timeout: float = 60.0,
):
    client = _get_async_client(api_key=api_key, base_url=base_url, timeout=timeout)

    extra_body: Dict[str, Any] = {
        "enable_thinking": enable_thinking,
        "chat_template_kwargs": {
            "thinking": enable_thinking,
            "enable_thinking": enable_thinking,
        },
    }
    if top_k is not None:
        extra_body["top_k"] = top_k

    create_kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        extra_body=extra_body,
        timeout=timeout,
    )

    if not stream:
        response = await client.chat.completions.create(**create_kwargs)
        msg = response.choices[0].message if response.choices else None
        reasoning_content = ""
        content = ""
        if msg:
            reasoning_content = (
                getattr(msg, "reasoning", None)
                or getattr(msg, "reasoning_content", None)
                or ""
            )
            content = getattr(msg, "content", None) or ""
        usage_info = getattr(response, "usage", None)
        return reasoning_content, content, usage_info

    stream_resp = await client.chat.completions.create(
        **create_kwargs,
        stream=True,
        stream_options={"include_usage": True},
    )

    reasoning_content = ""
    content = ""
    usage_info = None

    async for chunk in stream_resp:
        if getattr(chunk, "usage", None):
            usage_info = chunk.usage

        if not getattr(chunk, "choices", None):
            continue

        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            reasoning_content += delta.reasoning_content
        if hasattr(delta, "content") and delta.content:
            content += delta.content

    return reasoning_content, content, usage_info


def retry_llm(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    top_k: Optional[int] = None,
    enable_thinking: bool = False,
    stream: bool = True,
    max_retries: int = 3,
    timeout: float = 60.0,
):
    for attempt in range(1, max_retries + 1):
        try:
            reasoning_content, answer_content, usage = openai_interface(
                api_key=api_key,
                base_url=base_url,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                enable_thinking=enable_thinking,
                stream=stream,
                timeout=timeout,
            )

            if reasoning_content is not None and answer_content is not None:
                ## 兼容qwen3系列本地部署
                if reasoning_content == "" and "</think>\n\n" in answer_content:
                    reasoning_content = answer_content.split("</think>\n\n")[0]
                    answer_content = answer_content.split("</think>\n\n")[1]
                ## 兼容自有模型本地部署
                if reasoning_content == "" and "</think>\n" in answer_content:
                    reasoning_content = answer_content.split("</think>\n")[0]
                    answer_content = answer_content.split("</think>\n")[1]
                return reasoning_content, answer_content, usage

        except Exception as e:
            print(f"Attempt {attempt}/{max_retries} failed: {e}")

    print(f"Warning: Failed after {max_retries} retries.")
    return None, None, None


async def async_retry_llm(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    top_k: Optional[int] = None,
    enable_thinking: bool = False,
    stream: bool = True,
    max_retries: int = 3,
    timeout: float = 60.0,
):
    for attempt in range(1, max_retries + 1):
        try:
            reasoning_content, answer_content, usage = await async_openai_interface(
                api_key=api_key,
                base_url=base_url,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                enable_thinking=enable_thinking,
                stream=stream,
                timeout=timeout,
            )

            if reasoning_content is not None and answer_content is not None:
                if reasoning_content == "" and "</think>\n\n" in answer_content:
                    reasoning_content = answer_content.split("</think>\n\n")[0]
                    answer_content = answer_content.split("</think>\n\n")[1]
                if reasoning_content == "" and "</think>\n" in answer_content:
                    reasoning_content = answer_content.split("</think>\n")[0]
                    answer_content = answer_content.split("</think>\n")[1]
                return reasoning_content, answer_content, usage
        except Exception as e:
            print(f"Attempt {attempt}/{max_retries} failed: {e}")

    print(f"Warning: Failed after {max_retries} retries.")
    return None, None, None
