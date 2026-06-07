import React from 'react';
import type { GraphNode, MetricSemantics, SemanticsReport } from '../types/analysis.c09';

interface DetailPanelProps {
  selectedNode?: GraphNode | null;
  semanticsReport?: SemanticsReport | null;
  diagnostics?: Array<Record<string, unknown>>;
}

export function DetailPanelC09({ selectedNode, semanticsReport, diagnostics = [] }: DetailPanelProps) {
  if (!selectedNode) {
    return <div className="detail-panel empty">请选择一个节点查看详情</div>;
  }

  const metric = findMetricForNode(selectedNode, semanticsReport);
  const expression = selectedNode.data?.expression || metric?.expression;
  const dependsOn = selectedNode.data?.depends_on || metric?.depends_on || [];
  const aggregateFunctions = selectedNode.data?.aggregate_functions || metric?.aggregate_functions || [];
  const operators = selectedNode.data?.operators || metric?.operators || [];
  const description = selectedNode.data?.description || metric?.description;

  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div className="detail-panel__title">{selectedNode.label || selectedNode.id}</div>
        <div className="detail-panel__subtitle">{selectedNode.type}</div>
      </div>

      {expression ? (
        <section className="detail-section">
          <div className="detail-section__label">表达式</div>
          <pre className="detail-code">{expression}</pre>
        </section>
      ) : null}

      {dependsOn.length > 0 ? (
        <section className="detail-section">
          <div className="detail-section__label">上游依赖字段</div>
          <div className="tag-list">
            {dependsOn.map((dep) => (
              <span className="tag" key={dep}>{dep}</span>
            ))}
          </div>
        </section>
      ) : null}

      {aggregateFunctions.length > 0 ? (
        <section className="detail-section">
          <div className="detail-section__label">聚合函数</div>
          <div className="tag-list">
            {aggregateFunctions.map((fn) => (
              <span className="tag tag--strong" key={fn}>{fn}</span>
            ))}
          </div>
        </section>
      ) : null}

      {operators.length > 0 ? (
        <section className="detail-section">
          <div className="detail-section__label">算术操作</div>
          <div className="tag-list">
            {operators.map((op) => (
              <span className="tag" key={op}>{op}</span>
            ))}
          </div>
        </section>
      ) : null}

      {description ? (
        <section className="detail-section">
          <div className="detail-section__label">确定性口径说明</div>
          <div>{description}</div>
          <div className="detail-hint">说明文本仅来自 SQL 结构模板，血缘证据以 edges 为准。</div>
        </section>
      ) : null}

      {diagnostics.length > 0 ? (
        <section className="detail-section">
          <div className="detail-section__label">诊断信息</div>
          <ul>
            {diagnostics.map((item, index) => (
              <li key={index}>{String(item.code || item.message || JSON.stringify(item))}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function findMetricForNode(
  node: GraphNode,
  semanticsReport?: SemanticsReport | null,
): MetricSemantics | undefined {
  const metrics = semanticsReport?.metrics || [];
  if (metrics.length === 0) return undefined;

  const nodeName = String(node.data?.name || node.label || node.id.replace(/^output_column:/, '').replace(/^expression:/, ''));
  const entityId = node.entity_id || node.id;

  return metrics.find((metric) => {
    return (
      metric.entity_id === entityId ||
      metric.entity_id === `output_column:${nodeName}` ||
      metric.name === nodeName ||
      `expression:${metric.name}` === entityId ||
      `expression:${metric.name}` === node.id
    );
  });
}
