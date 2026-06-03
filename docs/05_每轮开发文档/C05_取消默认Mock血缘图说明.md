# C05 补充：取消默认 Mock 血缘图说明

## 本次改了什么

取消前端在未分析时展示默认 mock 血缘图。

现在只有 Analyze 返回真实 `backendGraph` 后，画布才会展示血缘节点和边。

## 为什么要改

默认 mock 血缘图会让用户误以为当前 SQL 已经完成解析。

而且这张图不一定和当前 SQL、当前视图、当前画布布局一致，容易出现“默认图是歪的”“最终节点位置不对”等误导。

## 当前规则

```text
未分析：空画布 + 提示信息
Analyze 成功：展示后端返回的真实图
某个视图没有对应数据：空图，不用其他视图冒充
```

## 本次怎么做

1. 初始 `pageMode` 改为 `empty`。
2. 初始 `analysisStatus` 改为 `none`。
3. 初始 `trustStatus` 改为 `untrusted`。
4. 初始 `positions` 改为空对象。
5. `visibleGraph` 在没有 `backendGraph` 时返回空图。
6. 补应用级测试：首次打开不出现默认血缘节点。

## 本次验证

```text
selectors + LineageCanvas targeted: 43 passed
frontend: 95 passed
npm run build: passed
```

## 涉及文件

```text
frontend/src/App.tsx
frontend/src/data/selectors.ts
frontend/src/data/__tests__/selectors.test.ts
frontend/src/components/__tests__/LineageCanvas.test.tsx
frontend/src/__tests__/analyzeFlow.test.tsx
```
