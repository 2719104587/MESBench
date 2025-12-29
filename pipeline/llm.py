from openai import OpenAI


def openai_interface(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    enable_thinking: bool = False,
    timeout: float = 60.0,
):
    # 初始化客户端
    client = OpenAI(
        base_url=base_url,  # 使用GLM的专用端点
        api_key=api_key,  # 替换为你在智谱平台获取的真实Key
        timeout=timeout,
    )

    # 创建聊天完成请求
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        extra_body={"enable_thinking": enable_thinking},
        stream=True,
        stream_options={"include_usage": True},
        timeout=timeout,
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


def retry_llm(
    api_key: str,
    base_url: str,
    prompt: str,
    model: str,
    max_tokens: int = 32768,
    temperature: float = 0.0,
    top_p: float = 0.0,
    enable_thinking: bool = False,
    max_retries: int = 3,
    timeout: float = 60.0,
):
    for attempt in range(1, max_retries + 1):
        try:
            reasoning_content, answer_content, usage = openai_interface(
                api_key,
                base_url,
                prompt,
                model,
                max_tokens,
                temperature,
                top_p,
                enable_thinking,
                timeout,
            )

            if reasoning_content is not None and answer_content is not None:
                # if reasoning_content == "" and "</think>\n" in answer_content:
                #     reasoning_content = answer_content.split("</think>\n")[0]
                #     answer_content = answer_content.split("</think>\n")[1]
                return reasoning_content, answer_content, usage

        except Exception as e:
            print(f"Attempt {attempt}/{max_retries} failed: {e}")

    print(f"Warning: Failed after {max_retries} retries.")
    return None, None, None
