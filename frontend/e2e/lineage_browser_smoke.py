"""Low-token browser smoke checks for the SQL lineage workbench.

This script wraps the local ``browser-harness`` command so a full UI smoke can
be run with one terminal command instead of a long interactive browser session.

Default check:
    python frontend/e2e/lineage_browser_smoke.py

Optional screenshot:
    python frontend/e2e/lineage_browser_smoke.py --screenshot C:/temp/lineage.png
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQL_FILE = Path(__file__).resolve().parent / "cases" / "single_table_column.sql"

DEFAULT_EXPECTED_NODES = [
    "dwd_order_di.order_no",
    "order_no",
    "dwd_order_di.user_id",
    "uid",
    "Query Result",
]

DEFAULT_EXPECTED_API_EDGES = [
    "physical_column:dwd_order_di.order_no->output_column:order_no",
    "output_column:order_no->query_result:final",
    "physical_column:dwd_order_di.user_id->output_column:uid",
    "output_column:uid->query_result:final",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a browser-harness smoke check against the lineage UI.",
    )
    parser.add_argument("--url", default="http://127.0.0.1:5173/", help="Frontend URL.")
    parser.add_argument("--dialect", default="hive", help="SQL dialect sent to the UI/API.")
    parser.add_argument("--view", default="Column", choices=["Column", "Table", "Subquery", "Expr"])
    parser.add_argument("--sql", help="Inline SQL. Overrides --sql-file.")
    parser.add_argument("--sql-file", default=str(DEFAULT_SQL_FILE), help="SQL file to load.")
    parser.add_argument(
        "--expect-node",
        action="append",
        default=None,
        help="Visible node label expected in the selected view. Can be repeated.",
    )
    parser.add_argument(
        "--expect-api-edge",
        action="append",
        default=None,
        help="Backend edge expected as source->target. Can be repeated.",
    )
    parser.add_argument("--expect-dom-edges", type=int, default=4, help="Expected visible SVG edge count.")
    parser.add_argument("--screenshot", help="Optional screenshot output path.")
    return parser.parse_args()


def read_sql(args: argparse.Namespace) -> str:
    if args.sql:
        return args.sql
    return Path(args.sql_file).read_text(encoding="utf-8")


def js_string(value: str) -> str:
    return json.dumps(value)


def browser_script(args: argparse.Namespace, sql: str) -> str:
    screenshot_line = ""
    if args.screenshot:
        screenshot_line = f"capture_screenshot({js_string(args.screenshot)})"

    expected_nodes = args.expect_node or DEFAULT_EXPECTED_NODES
    expected_edges = args.expect_api_edge or DEFAULT_EXPECTED_API_EDGES

    payload = {
        "url": args.url,
        "dialect": args.dialect,
        "view": args.view,
        "sql": sql,
        "expectedNodes": expected_nodes,
        "expectedApiEdges": expected_edges,
        "expectedDomEdges": args.expect_dom_edges,
    }

    return textwrap.dedent(
        f"""
        import json
        import time

        payload = {json.dumps(payload, ensure_ascii=False)}
        ensure_real_tab()
        new_tab(payload["url"])
        wait_for_load()

        result = js('''
        (async () => {{
          const payload = __PAYLOAD__;
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const buttonByText = (text) => Array.from(document.querySelectorAll('button'))
            .find((button) => (button.textContent || '').trim() === text);
          const buttonIncludes = (text) => Array.from(document.querySelectorAll('button'))
            .find((button) => (button.textContent || '').includes(text));

          if (!window.monaco || !window.monaco.editor?.getModels?.().length) {{
            throw new Error('Monaco editor model is not available');
          }}

          window.monaco.editor.getModels()[0].setValue(payload.sql);
          await sleep(100);

          const analyzeButton = buttonIncludes('Re-analyze') || buttonIncludes('Analyze');
          if (!analyzeButton) throw new Error('Analyze button not found');
          analyzeButton.click();

          const deadline = Date.now() + 8000;
          while (Date.now() < deadline) {{
            const text = document.body.innerText;
            if (text.includes('analyzed') && text.includes('trusted')) break;
            await sleep(150);
          }}

          const viewButton = buttonByText(payload.view);
          if (!viewButton) throw new Error(`${{payload.view}} view button not found`);
          viewButton.click();
          await sleep(600);

          const apiResponse = await fetch('/api/sql/analyze', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              sql: payload.sql,
              dialect: payload.dialect,
              analysis_level: 'column',
              default_catalog: 'default',
              default_schema: 'default',
              metadata_version: 'latest',
              case_sensitive: false,
              analysis_options: {{
                include_graph: true,
                include_semantics: false,
                include_diagnostics: true,
                include_source_location: true,
                include_expression_lineage: false,
              }},
            }}),
          }});
          const apiData = await apiResponse.json();

          const domNodes = Array.from(document.querySelectorAll('.node .title'))
            .map((element) => (element.textContent || '').trim());
          const domEdges = Array.from(document.querySelectorAll('path.edge'))
            .map((element) => element.getAttribute('class') || '');
          const apiEdges = (apiData.graph_view_model?.edges || [])
            .map((edge) => `${{edge.source}}->${{edge.target}}`);

          const missingNodes = payload.expectedNodes.filter((node) => !domNodes.includes(node));
          const missingApiEdges = payload.expectedApiEdges.filter((edge) => !apiEdges.includes(edge));
          const failures = [];
          if (!apiResponse.ok) failures.push(`API HTTP ${{apiResponse.status}}`);
          if (apiData.status !== 'success') failures.push(`API status ${{apiData.status}}`);
          if (missingNodes.length) failures.push(`missing DOM nodes: ${{missingNodes.join(', ')}}`);
          if (missingApiEdges.length) failures.push(`missing API edges: ${{missingApiEdges.join(', ')}}`);
          if (domEdges.length !== payload.expectedDomEdges) {{
            failures.push(`DOM edge count ${{domEdges.length}} != ${{payload.expectedDomEdges}}`);
          }}

          return {{
            ok: failures.length === 0,
            failures,
            page: {{ url: location.href, title: document.title }},
            apiStatus: apiData.status,
            view: payload.view,
            domNodes,
            domEdgeCount: domEdges.length,
            domEdgeClasses: domEdges,
            apiEdgeCount: apiEdges.length,
            apiEdges,
          }};
        }})()
        '''.replace('__PAYLOAD__', json.dumps(payload, ensure_ascii=False)))

        {screenshot_line}
        print("LINEAGE_BROWSER_SMOKE_RESULT_START")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("LINEAGE_BROWSER_SMOKE_RESULT_END")
        """
    ).strip()


def extract_result(stdout: str) -> dict:
    start = "LINEAGE_BROWSER_SMOKE_RESULT_START"
    end = "LINEAGE_BROWSER_SMOKE_RESULT_END"
    if start not in stdout or end not in stdout:
        raise RuntimeError(f"browser-harness did not print a parseable result:\n{stdout}")
    raw = stdout.split(start, 1)[1].split(end, 1)[0].strip()
    return json.loads(raw)


def main() -> int:
    args = parse_args()
    if not shutil.which("browser-harness"):
        print("browser-harness was not found on PATH.", file=sys.stderr)
        return 2

    sql = read_sql(args)
    script = browser_script(args, sql)
    completed = subprocess.run(
        ["browser-harness"],
        input=script,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )

    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return completed.returncode

    result = extract_result(completed.stdout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.screenshot:
        print(f"Screenshot: {args.screenshot}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
