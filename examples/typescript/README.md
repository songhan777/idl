# TypeScript 客户端接入示例

这是根据 `contracts/openapi.yaml` 生成类型的客户端薄封装，可放入现有前端项目后接入部署配置与认证模块。它覆盖本契约的五个操作、幂等请求头、条件写入、HTTP 错误及传输错误；不是包含认证登录、业务重试、持久化、监控和运行时校验的完整生产 SDK。

## 安装与验证

在仓库根目录使用 Node.js 24.19.0 和 pnpm 11.19.0：

```sh
pnpm install --frozen-lockfile --ignore-scripts
pnpm generate
pnpm validate
```

`package.json` 固定直接依赖版本，`pnpm-lock.yaml` 固定完整依赖树和完整性摘要。`pnpm-workspace.yaml` 将缓存放在仓库的 `.cache/pnpm/store`，禁用依赖安装脚本，并让运行前依赖检查失败时明确报错，避免执行检查命令时隐式重装。安装需要访问公共 npm registry 或由组织配置的镜像。升级工具链必须重新生成类型并运行全部检查。

本次验证版本：openapi-typescript 7.13.0、openapi-fetch 0.17.0、TypeScript 5.9.3。TypeScript 版本是本示例已验证的固定版本，不表示最新版本。

`schema.d.ts` 由 `pnpm generate` 生成，不手工编辑；契约修改与生成结果一并提交。`pnpm check:generated` 检查当前类型是否与契约一致。类型生成和类型检查遵循 [openapi-typescript 官方用法](https://openapi-ts.dev/introduction)；HTTP 调用使用 [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)。

## 接入应用

下面的 `runtimeConfig`、`authSession` 和 `submissionStore` 是应用集成点，必须连接已有配置、认证和持久化实现，不能直接粘贴成无依赖脚本。

```ts
import { createProjectClient } from "./client.ts";

const api = createProjectClient(
  runtimeConfig.apiBaseUrl,
  () => authSession.getAccessToken(),
);

// apiBaseUrl 例如 https://api.example.com；契约路径已经包含 /v1。
// 线上强制 HTTPS；仅 localhost、127.0.0.1、[::1] 允许 HTTP 本地开发。
const page = await api.list({ limit: 20 });
if (page.data.nextCursor !== null) {
  const nextPage = await api.list({ limit: 20, cursor: page.data.nextCursor });
  // 渲染下一页；游标只原样传回，前端不解码或拼接其内部字段。
}

const current = await api.get(projectId);
const updated = await api.update(
  projectId,
  { description: null }, // 清除；省略字段表示不修改。
  current.etag,          // 保留双引号，例如 "1"，不从 version 自行合成。
);

// 删除前由业务界面确认目标，使用实际读到的当前 ETag。
await api.remove(projectId, updated.etag);
```

每次请求调用 `getAccessToken`，不在客户端源码中写入令牌。回调应返回裸 access token，不含 `Bearer ` 前缀；需要登录或刷新时由认证模块处理。客户端使用 `credentials: "omit"`，与本契约的 Bearer 模式保持一致。若改为 BFF/cookie 架构，必须同时重新设计客户端、CORS 和 CSRF 约束。

客户端默认拒绝 HTTP 重定向，避免 API 被跳转到登录页或非预期地址。网关应按契约返回 401 与问题详情。跨域时服务端必须允许 `Authorization`、`Content-Type`、`If-Match`、`Idempotency-Key`，并暴露 `ETag`、`Location`、`Retry-After`、`X-Request-Id`，否则浏览器代码不能读取这些头。本契约要求所有响应发送 `X-Request-Id`；客户端错误对象仍允许它为 null，以便报告未遵守契约的代理响应或跨域配置问题。

## 创建操作与幂等键

创建前先为“逻辑提交”生成并持久保存 key 与原始请求体，随后才发送请求。下例中的 `loadOrCreate` 必须原子执行并按当前用户/租户隔离，保证双击、页面恢复和失败重试取得同一记录；它由业务持久层实现。

```ts
const submission = await submissionStore.loadOrCreate(draftId, () => ({
  key: crypto.randomUUID(),
  body: { displayName: "季度规划", description: null },
}));

const created = await api.create(submission.body, submission.key);
await submissionStore.markComplete(draftId, created.data.id);
```

`create` 不会内部生成 key，也不会自动重试。发生网络错误、超时或取消时，服务端可能已经完成写入；不能删除原 key 后创建一个新 key“重试”。业务层在幂等保留窗口内确认重试资格后，使用同一 key 和相同请求语义显式重发；修改请求体应建立新的逻辑提交。确定成功后持久标记结果；响应丢失或标记完成失败时可恢复原记录。不要持久保存 access token，也不要将包含敏感信息的提交草稿直接存入未保护的浏览器存储。

## 错误与取消

| 错误类 | 含义与调用方处理 |
| --- | --- |
| `ApiError` | 已收到 HTTP 失败响应；以 `status` 为准。`problem` 仅在媒体类型正确且响应为 JSON 对象时提供，字段仍视为不可信数据。 |
| `ProtocolError` | 成功状态与约定不符、成功体为空/不是 JSON/JSON 语法无效，或 ETag/Location 缺失或格式错误。写入结果可能已产生，不应无条件重新创建。 |
| `TransportError` | 网络、响应流中断、取消或超时；`kind` 为 `network`、`aborted`、`timeout`。浏览器中的 CORS/TLS/断网常统一表现为网络错误，需结合网关与浏览器排查。 |
| `AuthenticationError` | 获取令牌失败或令牌为空；交给认证状态处理，不伪装成服务端 401。 |

```ts
import { ApiError, ProtocolError, TransportError } from "./client.ts";

const controller = new AbortController();
try {
  const current = await api.get(projectId, { signal: controller.signal });
  await api.update(projectId, { displayName: "新名称" }, current.etag, {
    signal: controller.signal,
  });
} catch (error) {
  if (error instanceof ApiError && error.status === 412) {
    // 重新读取当前数据，展示冲突并让用户/业务策略合并；禁止静默覆盖。
  } else if (error instanceof TransportError) {
    // 展示取消/超时/网络状态；写请求的服务端结果可能未知。
  } else if (error instanceof ProtocolError) {
    // 报告协议异常。仅记录经允许的状态、requestId和错误类型，不记录令牌。
  } else {
    throw error;
  }
}
// 页面离开时可调用 controller.abort()。
```

每次方法调用默认有 10 秒 deadline；传入的用户取消信号通过 `AbortSignal.any` 与 deadline 合并。等待令牌和读取响应体也可被中断。中断等待不能强行终止认证回调内部已经启动的后台工作，因此认证模块应自行管理取消、并发刷新和清理。多个操作组成的业务流程需要调用方再传入统一总 deadline，不能依靠每次请求各自 10 秒计算总预算。

该实现依赖 Fetch、`AbortSignal.timeout` 与 `AbortSignal.any`；浏览器/WebView 上线前对目标版本做能力检查，缺失时采用经过验证的等价实现。[DOM 标准](https://dom.spec.whatwg.org/#interface-abortsignal) 定义了这些取消接口。浏览器挂起/休眠及事件循环阻塞会影响计时与回调执行；服务端也必须有自身的超时预算。

`ApiError.retryAfter` 保留原始响应头，由统一重试层解析秒数或 HTTP 日期；本契约服务端发送整数秒。该薄封装不自动重试 GET、写请求或 401，不会读取新 ETag 后自动重放 PATCH。重试策略需要同时判断操作是否允许重试、错误 code、幂等窗口、Retry-After 和剩余总预算。代理 HTML、非 JSON 或损坏的错误体仍保留真实 HTTP 状态；客户端不把原始错误页面插入 DOM。

## 类型与验证边界

生成类型只在编译时存在，不能验证真实响应。`readJson<T>` 的类型断言仅做 JSON 语法检查，不校验字段类型、范围、required、format、minProperties 或服务端是否执行了授权。即使 TypeScript 编译通过，运行时 JSON 仍可能与契约不一致。

接入无法充分信任的服务或需要严格边界校验时，在 `readJson` 边界添加支持本项目 JSON Schema 方言的运行时验证器，并测试未知字段兼容策略；服务端始终承担输入校验与授权。此示例也没有对响应体做流式字节上限限制，应由服务端/网关限制响应大小；如客户端需独立防御超大响应，则补充有界读取实现。

## 已执行的本地验证

已使用固定工具链生成真实 `schema.d.ts`，并通过 `tsc --noEmit`、生成一致性检查以及 13 个基于模拟 Fetch 的测试。覆盖请求头、幂等键显式复用、条件更新/删除、分页、problem+json、代理 HTML、损坏 JSON、ETag/Location、412、取消、超时、认证错误和响应流中断。

这些测试没有访问真实后端，也不证明数据库事务、租户隔离、CORS、网关规则或幂等存储已经上线；这些行为必须在接入环境按主文档验收。
