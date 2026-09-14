"""Documentation for the existing Flask views; does not change request validation.

Operations are keyed by Flask endpoint. Paths and path parameters come from the
registered URL map so blueprint prefixes have a single source of truth.
"""

from copy import deepcopy

from flask_smorest import Api


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
OBJECT = {"type": "object", "additionalProperties": True}
PASSWORD = {"type": "string", "format": "password", "writeOnly": True}
LANGUAGE = {"type": "string", "enum": ["zh-CN", "ja-JP", "en-US"]}
DIRECTION = {"type": "string", "enum": ["日→中", "中→日", "英→中", "中→英"]}
CONTEXT = {"class_id": INTEGER, "course_id": INTEGER}


def obj(properties, required=()):
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return schema


def array(items=OBJECT):
    return {"type": "array", "items": items}


def response(schema=OBJECT, description="成功", media_type="application/json"):
    return {"description": description, "content": {media_type: {"schema": schema}}}


def operation(summary, *, body=None, required=(), result=OBJECT, status=200,
              public=False, description="", media_type="application/json", query=None):
    doc = {
        "summary": summary,
        "responses": {str(status): response(result)},
    }
    if description:
        doc["description"] = description
    if public:
        doc["security"] = []
    if body is not None:
        doc["requestBody"] = {
            "required": bool(required),
            "content": {media_type: {"schema": obj(body, required)}},
        }
    if query:
        doc["parameters"] = [
            {"name": name, "in": "query", "required": False, "schema": schema}
            for name, schema in query.items()
        ]
    return doc


USER_CONTEXT = obj({"user": {**OBJECT, "nullable": True}, "contexts": array()})
PRACTICE = obj({"practice": OBJECT})
ARCHIVE = obj({"practice": OBJECT, "archive": OBJECT})
FEEDBACK_FIELDS = {name: STRING for name in ("pros", "cons", "suggestions", "overall")}
LIST_QUERY = {
    "student_no": {**STRING, "description": "仅教师和管理员可按学号筛选"},
    "limit": {**INTEGER, "default": 100, "maximum": 500},
}
CONTEXT_DESCRIPTION = (
    "class_id、course_id 指定所属班级和课程；开启 REQUIRE_PRACTICE_CONTEXT 时，"
    "仅有一个有效选课关系可自动选择，否则必须传入。数据访问受现有教学权限限制。"
)

OPERATIONS = {
    "health": operation("健康检查", public=True,
                        result=obj({"ok": BOOLEAN, "service": STRING})),
    "auth.login": operation("账号密码登录", public=True,
                            body={"login_id": STRING, "password": PASSWORD},
                            required=("login_id", "password"), result=USER_CONTEXT,
                            description="成功后浏览器保存 Session Cookie。首次登录需调用修改密码接口。"),
    "auth.me": operation("当前用户与教学关系", public=True, result=USER_CONTEXT,
                         description="未登录时 user 为 null，contexts 为空数组。"),
    "auth.managed_students": operation("教师或管理员可管理的学生",
                                       result=obj({"student_contexts": array()})),
    "auth.change_password": operation("修改当前账号密码",
                                       body={"current_password": PASSWORD, "new_password": PASSWORD},
                                       required=("current_password", "new_password"),
                                       result=obj({"user": OBJECT}),
                                       description="新密码长度由 PASSWORD_MIN_LENGTH 配置，且不能与原密码相同。"),
    "auth.logout": operation("退出登录", public=True, result=obj({"ok": BOOLEAN})),
    "practice.tts": operation("文本转语音",
                              body={"text": STRING, "lang": LANGUAGE, "voice": STRING, "speed": INTEGER},
                              required=("text",)),
    "practice.create_practice": operation(
        "创建练习（仅学生）", status=201, result=PRACTICE,
        body={"source_text": STRING, "direction": DIRECTION, "interval_seconds": INTEGER,
              "model_name": STRING, "prompt_params": obj({"role": STRING, "strictness": INTEGER,
                  "dimensions": array(STRING), "source_segments": array(STRING)}), **CONTEXT},
        required=("source_text",), description=CONTEXT_DESCRIPTION),
    "practice.list_practices": operation("练习列表", query={**LIST_QUERY, "status": STRING},
                                         result=obj({"practices": array()})),
    "practice.get_practice": operation(
        "练习详情与历史评价", result=obj({"practice": OBJECT, "archive": {**OBJECT, "nullable": True},
                                        "evaluation_versions": array(),
                                        "latest_evaluation": {**OBJECT, "nullable": True}})),
    "practice.upload_audio": operation(
        "上传录音并识别", body={"audio": {"type": "string", "format": "binary"}, "lang": LANGUAGE,
                             "segment_index": {"type": "integer", "minimum": 0}},
        required=("audio",), media_type="multipart/form-data",
        result=obj({"practice": OBJECT, "asr": OBJECT}),
        description="lang 默认使用练习目标语种；显式传入时必须与练习方向一致。文件上限由 MAX_UPLOAD_MB 配置。"
                    "创建练习时若传入 prompt_params.source_segments（必须完整对应原文），上传必须带从 0 开始的"
                    " segment_index，按句顺序上传；重录同一句替换该句，识别文本按顺序汇总。"),
    "practice.evaluate_practice": operation(
        "生成新一版 AI 评价", body={"asr_text": STRING},
        result=obj({"practice": OBJECT, "evaluation": OBJECT, "evaluation_version": OBJECT,
                    "archive": {**OBJECT, "nullable": True}}),
        description="省略 asr_text 时使用已有识别文本；必须有非空文本才能评价。逐句练习须先完成全部录音。"
                    "评价分数固定为 1–10，evaluation_json.structured 包含 score、overall、pros、cons、"
                    "suggestions、reference_translation。AI 格式或分数不合法返回 502，不保存无效版本。"),
    "practice.archive_practice": operation(
        "归档最新评价", body={"asr_text": STRING, "evaluation_version_id": INTEGER},
        result=ARCHIVE, status=201,
        description="省略参数时归档最新评价；传入的版本和文本必须与最新评价一致。重复归档同一版本返回 200。"),
    "practice.export_practices": operation("导出练习 CSV（教师、管理员）"),
    "practice.export_evaluation_versions": operation("导出评价版本 CSV（教师、管理员）"),
    "feedback.parse_feedback": operation("解析反馈文本", body={"raw_text": STRING},
                                         required=("raw_text",), result=obj(FEEDBACK_FIELDS)),
    "feedback.create_feedback_log": operation(
        "保存反馈", status=201, result=obj({"feedback_log": OBJECT}),
        body={"raw_text": STRING, "user_id": INTEGER, "task_id": STRING,
              "feedback_type": STRING, **FEEDBACK_FIELDS, **CONTEXT}, required=("raw_text",),
        description="教师和管理员必须传入反馈所属学生 user_id；学生使用自身账号。" + CONTEXT_DESCRIPTION),
    "feedback.list_feedback_logs": operation("反馈列表", query=LIST_QUERY,
                                             result=obj({"feedback_logs": array()})),
    "feedback.export_feedback_logs": operation("导出反馈 CSV（教师、管理员）"),
    "prompt.prompt_presets": operation("提示词预设", result=obj({"presets": array(),
                                                                 "default_dimensions": array(STRING)})),
    "prompt.build_prompt": operation("生成评价提示词",
                                     body={"role": STRING, "direction": DIRECTION,
                                           "strictness": INTEGER, "dimensions": array(STRING)},
                                     result=obj({"prompt": STRING})),
    "stats.summary": operation("学习统计", result=obj({
        "total_practices": INTEGER, "completed_practices": INTEGER, "archived_practices": INTEGER,
        "estimated_minutes": INTEGER, "average_score": obj({"label": STRING,
        "numeric": {"type": "number", "nullable": True}}), "recent": array(),
    })),
    "llm.list_conversations": operation("当前用户的对话历史", query={"before": INTEGER}),
    "llm.create_conversation": operation("新建独立会话", status=201),
    "llm.get_conversation": operation("读取本人会话消息", query={"before": INTEGER},
        description="每页最多 50 轮，before 为轮次序号；返回 busy、has_more。其他用户的会话统一返回 404。"),
    "llm.chat": operation("发送消息并保存回复", body={
        "conversation_id": {"type": "string", "format": "uuid"},
        "request_id": {"type": "string", "format": "uuid"},
        "message": {"type": "string", "maxLength": 8000},
        "expected_version": {"type": "integer", "minimum": 0},
    }, required=("conversation_id", "request_id", "message", "expected_version"),
        description="必须登录。历史上下文由服务端读取，不接收客户端历史。相同请求 ID 和原文幂等；"
                    "冲突或会话忙返回 409。AI 失败返回 502，用户消息仍保存，可使用原请求 ID 重试。"),
    "admin.overview": operation("账号与教学组织总览", result=obj({
        name: array() for name in ("users", "terms", "classes", "courses", "enrollments", "assignments")
    })),
    "admin.audit_logs": operation("最近 500 条审计记录", result=obj({"audit_logs": array()})),
    "admin.create_user": operation(
        "创建账号", status=201,
        body={"login_id": STRING, "name": STRING, "student_no": STRING, "password": PASSWORD,
              "role": {"type": "string", "enum": ["student", "teacher", "admin"], "default": "student"}},
        required=("login_id", "name"), result=obj({"user": OBJECT, "initial_password": STRING}),
        description="不传 password 时自动生成初始密码；新账号首次登录必须修改密码。"),
    "admin.update_user": operation("修改账号姓名或启用状态", body={"name": STRING, "is_active": BOOLEAN},
                                   result=obj({"user": OBJECT})),
    "admin.reset_password": operation("重置账号密码", body={"password": PASSWORD},
                                      result=obj({"user": OBJECT, "initial_password": STRING}),
                                      description="不传 password 时自动生成。旧会话失效，下次登录必须修改密码。"),
    "admin.import_students": operation(
        "导入学生名单", body={"file": {"type": "string", "format": "binary"}}, required=("file",),
        media_type="multipart/form-data", result=obj({"imported": array(), "errors": array(), "count": INTEGER}),
        description="支持 CSV/XLSX，单次最多 5000 人。必需列：学号、姓名、班级、课程、学期；"
                    "模板见 docs/student-import-template.csv。逐行错误在 errors 中返回。"),
}

for endpoint, label, key in (
    ("create_term", "学期", "term"), ("create_class", "班级", "class_group"),
    ("create_course", "课程", "course"),
):
    fields = {"code": STRING, "name": STRING}
    required = ["code"]
    if endpoint != "create_term":
        fields["term_id"] = INTEGER
        required.append("term_id")
    OPERATIONS[f"admin.{endpoint}"] = operation(
        f"创建{label}", body=fields, required=required, result=obj({key: OBJECT}), status=201)

for endpoint, person, key in (
    ("create_enrollment", "student_id", "enrollment"),
    ("create_assignment", "teacher_id", "assignment"),
):
    OPERATIONS[f"admin.{endpoint}"] = operation(
        "保存学生选课" if person == "student_id" else "保存教师授课范围",
        body={person: INTEGER, "term_id": INTEGER, **CONTEXT},
        required=(person, "term_id", "class_id", "course_id"), result=obj({key: OBJECT}), status=201)

for endpoint, key in (
    ("update_assignment", "assignment"), ("update_enrollment", "enrollment"),
    ("update_term", "term"), ("update_class", "class_group"), ("update_course", "course"),
):
    OPERATIONS[f"admin.{endpoint}"] = operation(
        "更新启用状态", body={"is_active": BOOLEAN}, result=obj({key: OBJECT}))

OPERATIONS["practice.archive_practice"]["responses"]["200"] = response(ARCHIVE, "该版本已归档")
OPERATIONS["practice.evaluate_practice"]["responses"]["502"] = response(
    obj({"error": STRING}), "AI 评价格式或分数不符合要求")
for endpoint in ("practice.export_practices", "practice.export_evaluation_versions",
                 "feedback.export_feedback_logs"):
    OPERATIONS[endpoint]["responses"] = {"200": response(STRING, "UTF-8 BOM 编码的 CSV 文件", "text/csv")}

OPERATIONS["llm.chat"]["responses"]["409"] = response(obj({"error": STRING}), "会话版本、请求内容冲突或正在回复")
OPERATIONS["llm.chat"]["responses"]["502"] = response(OBJECT, "AI 失败，返回已保存的会话和失败轮次")

from .services.settings import FIELDS, SECRETS

SETTINGS_FIELDS = {
    key: {**(BOOLEAN if isinstance(default, bool) else INTEGER if isinstance(default, int)
          else PASSWORD if key in SECRETS else STRING), "nullable": True}
    for key, default in FIELDS.items()
}
OPERATIONS.update({
    "system.get_settings": operation("读取系统服务配置（密钥不回显）"),
    "system.update_settings": operation("保存系统服务配置", body=SETTINGS_FIELDS,
        description="仅管理员。密钥加密保存，留空保留原值。传 null 删除该字段的 Web 覆盖，恢复环境配置。未提交字段保持不变。Web 覆盖优先于环境配置，后续请求立即生效。"),
    "system.test_service": operation("测试已保存的真实服务", description=(
        "仅管理员。service 为 llm 或 asr；测试始终关闭模拟模式。llm 发送 JSON text；"
        "asr 发送 multipart audio 和 lang。录音不超过 1 MB，讯飞要求 16kHz/16bit/单声道 PCM/WAV，"
        "最多 30 秒。返回调用结果及 elapsed_ms；上游失败返回 502。")),
})
OPERATIONS["system.test_service"]["requestBody"] = {"content": {
    "application/json": {"schema": obj({"text": STRING})},
    "multipart/form-data": {"schema": obj({"audio": {"type": "string", "format": "binary"},
                                           "lang": LANGUAGE}, ("audio",))},
}}
OPERATIONS["system.test_service"]["responses"]["502"] = response(obj({"error": STRING}), "真实服务调用失败")

TAGS = {
    "system": "系统配置", "health": "系统", "auth": "登录与账号", "practice": "口译练习", "feedback": "反馈档案",
    "prompt": "提示词", "stats": "学习统计", "admin": "管理后台", "llm": "AI 对话",
}


def register_openapi(app):
    api = Api(app, spec_kwargs={
        "info": {"description": (
            "先在登录接口执行 Try it out，浏览器将自动携带 Session Cookie。"
            "首次登录后请先修改初始密码。学生只能访问自己的数据，教师按授课范围访问，"
            "管理后台仅限管理员。文档描述现有接口行为，不额外执行参数校验。"
        )},
        "security": [{"sessionCookie": []}],
        "tags": [{"name": name} for name in TAGS.values()],
    })
    api.spec.components.security_scheme("sessionCookie", {
        "type": "apiKey", "in": "cookie", "name": app.config["SESSION_COOKIE_NAME"],
        "description": "通过 /api/auth/login 登录取得；浏览器自动携带，无需在 Authorize 中手动填写。",
    })
    api.spec.components.schema("APIError", obj({"error": STRING}, ("error",)))
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in OPERATIONS:
            continue
        doc = deepcopy(OPERATIONS[rule.endpoint])
        group = rule.endpoint.split(".")[0]
        doc["tags"] = [TAGS[group]]
        if group in {"admin", "system"}:
            doc["description"] = "仅管理员可用。" + doc.get("description", "")
        errors = {"400": "请求参数或业务状态不合法", "500": "内部错误或上游服务调用失败"}
        if doc.get("security") != [] or rule.endpoint == "auth.login":
            errors.update({"401": "未登录、会话失效或账号密码错误", "403": "权限不足、账号禁用或需先修改密码"})
        if rule.arguments:
            errors["404"] = "资源不存在"
        for status, description in errors.items():
            doc["responses"][status] = response({"$ref": "#/components/schemas/APIError"}, description)
        if "requestBody" in doc and "multipart/form-data" in doc["requestBody"]["content"]:
            doc["responses"]["413"] = {"description": "上传内容超过 MAX_UPLOAD_MB 配置的上限"}
        methods = {}
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            methods[method.lower()] = {**doc, "operationId": f"{rule.endpoint.replace('.', '_')}_{method.lower()}"}
        api.spec.path(rule=rule, operations=methods)
