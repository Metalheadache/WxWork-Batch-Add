# -*- coding: utf-8 -*-
"""模板清单 —— 校准向导与自动化引擎的单一事实来源。

每个模板描述一个需要在屏幕上识别的界面元素。校准向导按此顺序引导用户
从自己的屏幕上框选出这些元素;引擎按名字查找它们。

group:
  core     必需,无论是否打标签都要
  optional 可跳过(有更稳妥的兜底方案)
  tag      仅当「添加标签」开启时需要
"""

TEMPLATE_SPECS = [
    {
        "name": "search_box", "group": "core",
        "label": "搜索框",
        "hint": "框选「添加客户」弹窗顶部那条带放大镜的『手机号/邮箱』输入框。",
    },
    {
        "name": "result_row", "group": "core",
        "label": "搜索结果行图标",
        "hint": "先在搜索框输入一个真实号码回车,出现结果行后,框选结果行最左边那个绿色的微信小图标。",
    },
    {
        "name": "add_button", "group": "core",
        "label": "「添加为联系人」按钮",
        "hint": "点开一个『非好友』的联系人卡片,框选底部蓝色的「添加为联系人」按钮(只框文字+按钮,别框到外面)。",
    },
    {
        "name": "msg_button", "group": "core",
        "label": "「发消息」按钮",
        "hint": "点开一个『已是好友』的联系人卡片,框选底部蓝色的「发消息」按钮。",
    },
    {
        "name": "added_flag", "group": "core",
        "label": "「已添加」字样",
        "hint": "搜索一个已是好友的号码,框选结果行右侧灰色的「已添加」两个字。",
    },
    {
        "name": "invite_send", "group": "core",
        "label": "「发送」按钮",
        "hint": "走到『发送添加邀请』弹窗,框选那个蓝色的「发送」大按钮。",
    },
    {
        "name": "error_confirm", "group": "core",
        "label": "错误弹窗「确定」",
        "hint": "搜索一个无效号码触发『该用户不存在』弹窗,框选里面蓝色的「确定」按钮。",
    },
    {
        "name": "error_flag", "group": "optional",
        "label": "错误提示文字(可跳过)",
        "hint": "同一个『该用户不存在』弹窗,框选「无法找到该用户…」这行提示文字。用于二次确认,可跳过。",
    },
    {
        "name": "invite_input", "group": "optional",
        "label": "验证语输入框(可跳过)",
        "hint": "『发送添加邀请』弹窗里那条验证语输入框。跳过的话程序会用相对『发送』按钮的位置估算,一般也够用。",
    },
    {
        "name": "open_tag_row", "group": "tag",
        "label": "「设置标签」行",
        "hint": "在『非好友』卡片上,框选「设置标签」这一行文字(带右侧的 > 箭头也行)。",
    },
    {
        "name": "panel_search", "group": "tag",
        "label": "标签面板「搜索」框",
        "hint": "点「设置标签」打开右侧面板,框选面板顶部的「搜索」输入框。",
    },
    {
        "name": "panel_first_chip", "group": "tag",
        "label": "第一个标签",
        "hint": "在标签面板里,框选『个人标签』区域最靠前的那一个标签按钮(程序会在这里点选你指定的标签)。",
    },
    {
        "name": "panel_confirm", "group": "tag",
        "label": "标签面板「确定」",
        "hint": "框选标签面板底部蓝色的「确定」按钮。",
    },
]

BY_NAME = {s["name"]: s for s in TEMPLATE_SPECS}


def required_names(enable_tag):
    """当前配置下必须存在的模板名(用于运行前自检)。"""
    names = []
    for s in TEMPLATE_SPECS:
        if s["group"] == "core":
            names.append(s["name"])
        elif s["group"] == "tag" and enable_tag:
            names.append(s["name"])
    return names


def specs_for(enable_tag, include_optional=True):
    """校准向导要走的条目顺序。"""
    out = []
    for s in TEMPLATE_SPECS:
        if s["group"] == "core":
            out.append(s)
        elif s["group"] == "optional" and include_optional:
            out.append(s)
        elif s["group"] == "tag" and enable_tag:
            out.append(s)
    return out
