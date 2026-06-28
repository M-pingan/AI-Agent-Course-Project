import { useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const architectureCards = [
  {
    title: "LLM 层",
    body: "理解页面语义、执行结构化抽取、生成附注摘要，并与规则结果协同输出。",
  },
  {
    title: "Tools 层",
    body: "负责 PDF 解析、字段抽取、质量校验、导出 JSON/CSV 等基础能力。",
  },
  {
    title: "Knowledge Base 层",
    body: "内置资产负债表字段字典、管理层关键词、附注类别规则与 Prompt 模板。",
  },
  {
    title: "Workflow 层",
    body: "将上传、解析、分类、抽取、校验、展示与导出串成稳定演示链路。",
  },
];

const flowSteps = [
  "上传年报 PDF",
  "提取页面文本",
  "判断页面类型",
  "抽取三类结果",
  "执行规则校验",
  "展示并导出结果",
];

function App() {
  const [file, setFile] = useState(null);
  const [taskId, setTaskId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("请先选择一份 PDF 年报文件。");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const uploadResponse = await fetch(`${API_BASE_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });
      const uploadData = await uploadResponse.json();
      if (!uploadResponse.ok) {
        throw new Error(uploadData.detail || "上传失败。");
      }

      setTaskId(uploadData.task_id);
      const resultResponse = await fetch(`${API_BASE_URL}/api/result/${uploadData.task_id}`);
      const resultData = await resultResponse.json();
      if (!resultResponse.ok) {
        throw new Error(resultData.detail || "结果获取失败。");
      }

      setResult(resultData.result);
    } catch (err) {
      setError(err.message || "处理失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  const openExport = (format) => {
    if (!taskId) {
      setError("当前没有可导出的任务结果。");
      return;
    }
    window.open(`${API_BASE_URL}/api/export/${taskId}?format=${format}`, "_blank");
  };

  return (
    <div className="page-shell">
      <div className="backdrop backdrop-a" />
      <div className="backdrop backdrop-b" />

      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">AI Agent Course Project</p>
          <h1>企业年报结构化提取智能体</h1>
          <p className="hero-text">
            面向课程题目 8 的专业智能体演示系统，围绕
            <strong> 资产负债表、管理层变动、附注摘要 </strong>
            三类任务，展示 `LLM + Tools + Knowledge Base + Workflow` 的完整链路。
          </p>
        </div>

        <form className="upload-panel" onSubmit={handleUpload}>
          <label className="upload-label">
            <span>上传中文上市公司年报 PDF</span>
            <input
              type="file"
              accept="application/pdf"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "处理中..." : "开始解析"}
          </button>
          <p className="micro-copy">建议先使用可搜索版 PDF，扫描版文档需要补充 OCR。</p>
        </form>
      </header>

      <main className="content-grid">
        <section className="card card-wide">
          <div className="section-head">
            <h2>Agent 四层架构</h2>
            <span>答辩可直接讲这一块</span>
          </div>
          <div className="architecture-grid">
            {architectureCards.map((card) => (
              <article className="architecture-card" key={card.title}>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="section-head">
            <h2>工作流</h2>
            <span>展示智能体不是聊天框</span>
          </div>
          <ol className="flow-list">
            {flowSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>

        <section className="card">
          <div className="section-head">
            <h2>当前状态</h2>
            <span>上传后自动刷新结果</span>
          </div>
          <div className="status-box">
            <p>
              <strong>任务编号：</strong>
              {taskId || "尚未开始"}
            </p>
            <p>
              <strong>处理状态：</strong>
              {loading ? "处理中" : result?.status || "待上传"}
            </p>
            {error ? <p className="error-text">{error}</p> : null}
          </div>
          <div className="action-row">
            <button type="button" className="secondary-btn" onClick={() => openExport("json")}>
              导出 JSON
            </button>
            <button type="button" className="secondary-btn" onClick={() => openExport("csv")}>
              导出 CSV
            </button>
          </div>
        </section>

        <section className="card card-wide">
          <div className="section-head">
            <h2>解析结果</h2>
            <span>课程展示重点区域</span>
          </div>
          {result ? (
            <div className="result-stack">
              <div className="meta-grid">
                <div className="meta-card">
                  <span>公司名称</span>
                  <strong>{result.company_name || "未识别"}</strong>
                </div>
                <div className="meta-card">
                  <span>报告期</span>
                  <strong>{result.report_period || "未识别"}</strong>
                </div>
                <div className="meta-card">
                  <span>页面分析数</span>
                  <strong>{result.page_analyses?.length || 0}</strong>
                </div>
              </div>

              <ResultTable
                title="资产负债表字段"
                columns={["字段", "值", "页码", "原文片段"]}
                rows={(result.balance_sheet || []).map((item) => [
                  item.field_name,
                  item.value || "未抽取",
                  item.source_page || "-",
                  item.source_excerpt || "-",
                ])}
              />

              <ResultTable
                title="管理层变动"
                columns={["姓名", "变动类型", "现职位", "生效时间", "页码"]}
                rows={(result.management_changes || []).map((item) => [
                  item.name || "待确认",
                  item.change_type || "-",
                  item.current_role || "-",
                  item.effective_date || "-",
                  item.source_page || "-",
                ])}
              />

              <ResultTable
                title="附注摘要"
                columns={["类别", "页码范围", "摘要", "风险提示"]}
                rows={(result.notes_summary || []).map((item) => [
                  item.category,
                  item.page_range || "-",
                  item.summary || "-",
                  item.risk_hint || "-",
                ])}
              />

              <ul className="quality-list">
                {(result.quality_checks || []).map((item) => (
                  <li key={`${item.code}-${item.message}`}>
                    <strong>[{item.level}]</strong> {item.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="empty-state">
              <p>上传年报后，这里会展示结构化抽取结果、质量检查信息和导出入口。</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function ResultTable({ title, columns, rows }) {
  return (
    <section className="result-card">
      <h3>{title}</h3>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row, index) => (
                <tr key={`${title}-${index}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${title}-${index}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length}>暂无数据</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default App;

