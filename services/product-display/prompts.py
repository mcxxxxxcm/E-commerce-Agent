"""
商品展示图生成模块 — Prompt 模板
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 图像分析 Prompt
# ---------------------------------------------------------------------------

IMAGE_ANALYSIS_SYSTEM = """你是一个专业的电商商品视觉分析师。你需要仔细观察商品图片，提取以下信息：

1. **品类 (category)**: 商品属于什么类目（服饰、数码、美妆、家居、食品等）
2. **材质 (material)**: 商品的材质/面料（如果可辨识）
3. **主色调 (color_palette)**: 商品的主色调和配色方案
4. **风格 (style)**: 设计风格（简约、复古、科技、轻奢、国潮等）
5. **视觉特征 (features)**: 显著的视觉特征（形状、纹理、图案、品牌标识等）
6. **使用场景 (use_scenario)**: 适合的使用场景
7. **视觉氛围 (mood)**: 图片传递出的氛围感

请用中文输出，JSON 格式。"""


def build_analysis_prompt(product_name: str = "", category: str = "") -> str:
    """构建图像分析 prompt"""
    parts = ["请分析这张商品图片。"]
    if product_name:
        parts.append(f"商品名称：{product_name}")
    if category:
        parts.append(f"参考品类：{category}")
    parts.append("请输出 JSON 格式的分析结果。")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 展示图生成 Prompt
# ---------------------------------------------------------------------------

IMAGE_GEN_TEMPLATE = """Professional e-commerce product photography of {product_desc}.
Style: {style}, {mood} atmosphere.
{scenario}
Studio lighting, clean {background} background, 8K resolution, commercial photography quality,
product-focused composition, no text overlay, no watermark."""


def build_image_gen_prompt(analysis: dict, product_name: str = "") -> str:
    """根据分析结果构建 DALL-E / SD 生成 prompt"""
    product_desc = product_name or analysis.get("category", "product")
    style = analysis.get("style", "modern")
    mood = analysis.get("mood", "professional")
    scenario = analysis.get("use_scenario", "")
    features = analysis.get("features", [])
    colors = analysis.get("color_palette", [])

    feature_text = ", ".join(features[:3]) if features else ""
    color_text = ", ".join(colors[:3]) if colors else ""

    scenario_line = f"Scene: {scenario}." if scenario else ""
    feature_line = f"Product features: {feature_text}." if feature_text else ""
    color_line = f"Color scheme: {color_text}." if color_text else ""

    background = "white"
    # 深色商品用浅色背景，反之亦然
    dark_colors = {"black", "navy", "dark", "charcoal", "deep"}
    if any(c.lower() in dark_colors for c in colors):
        background = "light gray"

    return IMAGE_GEN_TEMPLATE.format(
        product_desc=f"{product_desc}, {feature_text}".strip(", "),
        style=style,
        mood=mood,
        scenario=f"{scenario_line} {feature_line} {color_line}".strip(),
        background=background,
    )


# ---------------------------------------------------------------------------
# 商品描述生成 Prompt
# ---------------------------------------------------------------------------

DESCRIPTION_SYSTEM = """你是一个资深的电商文案策划师。根据商品信息和分析结果，撰写吸引人的商品描述。"""


def build_description_prompt(analysis: dict, product_name: str = "", brand_style: str = "") -> str:
    """构建商品描述生成 prompt"""
    parts = ["请根据以下商品信息，撰写一段吸引人的商品描述文案（200-500字）。"]
    parts.append("要求：突出卖点、场景化表达、语言生动、适合电商平台展示。")

    if brand_style:
        parts.append(f"\n品牌调性：{brand_style}")

    parts.append(f"\n商品品类：{analysis.get('category', '通用')}")
    parts.append(f"材质：{analysis.get('material', '待确认')}")
    parts.append(f"风格：{analysis.get('style', '现代')}")
    parts.append(f"视觉特征：{', '.join(analysis.get('features', []))}")
    parts.append(f"使用场景：{analysis.get('use_scenario', '日常')}")
    parts.append(f"氛围：{analysis.get('mood', '专业')}")

    if product_name:
        parts.append(f"\n商品名称：{product_name}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 上架内容生成 Prompt
# ---------------------------------------------------------------------------

LISTING_SYSTEM = """你是一个专业的电商运营专家。根据商品信息生成电商平台上架所需的关键内容。"""


def build_listing_prompt(
    analysis: dict,
    description: str = "",
    product_name: str = "",
    platform: str = "taobao",
) -> str:
    """构建上架内容生成 prompt"""
    platform_names = {
        "taobao": "淘宝",
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "jd": "京东",
    }
    platform_cn = platform_names.get(platform, platform)

    parts = [f"请根据以下商品信息，生成{platform_cn}平台上架所需的关键内容。"]
    parts.append("请以 JSON 格式输出，包含以下字段：")

    fields = [
        ("title", "商品标题（含SEO关键词，30-60字）"),
        ("short_title", "短标题（≤30字）"),
        ("selling_points", "核心卖点列表（3-5条）"),
        ("bullet_features", "功能/特性要点列表（4-6条）"),
        ("attributes", "属性键值对（如 品牌:XX, 材质:XX, 规格:XX）"),
        ("keywords", "搜索关键词列表（5-10个）"),
        ("suggested_price_range", "建议价格区间"),
        ("target_audience", "目标人群描述"),
    ]
    parts.append("\n".join(f"- {name}: {desc}" for name, desc in fields))

    parts.append(f"\n商品品类：{analysis.get('category', '通用')}")
    parts.append(f"材质：{analysis.get('material', '')}")
    parts.append(f"风格：{analysis.get('style', '')}")
    parts.append(f"特征：{', '.join(analysis.get('features', []))}")
    parts.append(f"场景：{analysis.get('use_scenario', '')}")

    if product_name:
        parts.append(f"\n商品名称：{product_name}")
    if description:
        parts.append(f"\n商品描述参考：\n{description}")

    return "\n".join(parts)
