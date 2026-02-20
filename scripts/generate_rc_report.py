#!/usr/bin/env python3
"""
RC Burn-in Report Generator - QA-010
=====================================

Aggregates burn-in test results and generates comprehensive reports.

Usage:
    python scripts/generate_rc_report.py --input roadmap_ctp/burn_in/ --output docs/RC_REPORT.md
    python scripts/generate_rc_report.py --aggregate --input roadmap_ctp/burn_in/
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a JSON file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load {path}: {e}")
        return None


def find_burn_in_summaries(directory: Path) -> List[Path]:
    """Find all burn-in summary JSON files in directory."""
    pattern = "burn_in_summary_*.json"
    return sorted(directory.glob(pattern))


def calculate_stability_metrics(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate aggregate stability metrics from multiple summaries."""
    if not summaries:
        return {}
    
    metrics = {
        "total_runs": 0,
        "total_cycles": 0,
        "successful_cycles": 0,
        "failed_cycles": 0,
        "gate_results": {},
        "duration_stats": {
            "total_seconds": 0,
            "min_seconds": float('inf'),
            "max_seconds": 0,
        },
        "pass_rate_trend": [],
        "first_run": None,
        "last_run": None,
    }
    
    for summary in summaries:
        metadata = summary.get("metadata", {})
        summary_data = summary.get("summary", {})
        gate_stats = summary.get("gate_statistics", {})
        
        # Track timestamps
        generated_at = metadata.get("generated_at")
        if generated_at:
            if metrics["first_run"] is None or generated_at < metrics["first_run"]:
                metrics["first_run"] = generated_at
            if metrics["last_run"] is None or generated_at > metrics["last_run"]:
                metrics["last_run"] = generated_at
        
        # Aggregate cycle counts
        metrics["total_runs"] += 1
        metrics["total_cycles"] += summary_data.get("cycles_run", 0)
        metrics["successful_cycles"] += summary_data.get("successful_cycles", 0)
        metrics["failed_cycles"] += summary_data.get("failed_cycles", 0)
        
        # Duration stats
        duration = summary_data.get("total_duration_seconds", 0)
        metrics["duration_stats"]["total_seconds"] += duration
        metrics["duration_stats"]["min_seconds"] = min(
            metrics["duration_stats"]["min_seconds"], duration
        )
        metrics["duration_stats"]["max_seconds"] = max(
            metrics["duration_stats"]["max_seconds"], duration
        )
        
        # Pass rate trend
        pass_rate = summary_data.get("cycle_pass_rate", 0)
        metrics["pass_rate_trend"].append(pass_rate)
        
        # Gate results aggregation
        for gate_name, gate_data in gate_stats.items():
            if gate_name not in metrics["gate_results"]:
                metrics["gate_results"][gate_name] = {
                    "total_runs": 0,
                    "total_passes": 0,
                    "total_failures": 0,
                    "pass_rates": [],
                    "durations": [],
                }
            
            metrics["gate_results"][gate_name]["total_runs"] += gate_data.get("runs", 0)
            metrics["gate_results"][gate_name]["total_passes"] += gate_data.get("passes", 0)
            metrics["gate_results"][gate_name]["total_failures"] += gate_data.get("failures", 0)
            
            if gate_data.get("avg_pass_rate") is not None:
                metrics["gate_results"][gate_name]["pass_rates"].append(
                    gate_data["avg_pass_rate"]
                )
            
            if gate_data.get("avg_duration_seconds") is not None:
                metrics["gate_results"][gate_name]["durations"].append(
                    gate_data["avg_duration_seconds"]
                )
    
    # Calculate averages
    if metrics["duration_stats"]["min_seconds"] == float('inf'):
        metrics["duration_stats"]["min_seconds"] = 0
    
    metrics["overall_pass_rate"] = (
        metrics["successful_cycles"] / metrics["total_cycles"] * 100
        if metrics["total_cycles"] > 0 else 0
    )
    
    metrics["avg_pass_rate"] = (
        sum(metrics["pass_rate_trend"]) / len(metrics["pass_rate_trend"])
        if metrics["pass_rate_trend"] else 0
    )
    
    # Calculate gate averages
    for gate_name in metrics["gate_results"]:
        gate = metrics["gate_results"][gate_name]
        gate["avg_pass_rate"] = (
            sum(gate["pass_rates"]) / len(gate["pass_rates"])
            if gate["pass_rates"] else None
        )
        gate["avg_duration"] = (
            sum(gate["durations"]) / len(gate["durations"])
            if gate["durations"] else None
        )
        gate["reliability"] = (
            gate["total_passes"] / gate["total_runs"] * 100
            if gate["total_runs"] > 0 else 0
        )
    
    return metrics


def assess_stability(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Assess overall stability based on metrics."""
    assessment = {
        "rating": "UNKNOWN",
        "score": 0,
        "recommendation": "",
        "concerns": [],
        "strengths": [],
    }
    
    overall_rate = metrics.get("overall_pass_rate", 0)
    avg_rate = metrics.get("avg_pass_rate", 0)
    
    # Calculate score (0-100)
    score = (overall_rate * 0.6 + avg_rate * 0.4)
    assessment["score"] = round(score, 1)
    
    # Determine rating
    if score >= 99:
        assessment["rating"] = "EXCELLENT"
        assessment["recommendation"] = "RC is highly stable. Ready for V1.0 release."
        assessment["strengths"].append("Exceptional stability across all test cycles")
    elif score >= 95:
        assessment["rating"] = "VERY_GOOD"
        assessment["recommendation"] = "RC shows strong stability. Minor issues may need attention."
        assessment["strengths"].append("High reliability in test cycles")
    elif score >= 90:
        assessment["rating"] = "GOOD"
        assessment["recommendation"] = "RC is stable with some issues. Review failures before release."
        assessment["concerns"].append("Some test failures detected")
    elif score >= 75:
        assessment["rating"] = "FAIR"
        assessment["recommendation"] = "RC has stability concerns. Investigation recommended."
        assessment["concerns"].append("Multiple failures detected")
    else:
        assessment["rating"] = "POOR"
        assessment["recommendation"] = "RC is not stable enough for release. Significant issues found."
        assessment["concerns"].append("High failure rate detected")
    
    # Gate-specific analysis
    for gate_name, gate_data in metrics.get("gate_results", {}).items():
        reliability = gate_data.get("reliability", 0)
        if reliability < 90:
            assessment["concerns"].append(f"{gate_name}: {reliability:.1f}% reliability")
        elif reliability >= 99:
            assessment["strengths"].append(f"{gate_name}: {reliability:.1f}% reliability")
    
    # Trend analysis
    pass_rates = metrics.get("pass_rate_trend", [])
    if len(pass_rates) >= 3:
        # Check for declining trend
        recent = pass_rates[-3:]
        if all(recent[i] > recent[i+1] for i in range(len(recent)-1)):
            assessment["concerns"].append("Declining stability trend in recent runs")
        elif all(recent[i] <= recent[i+1] for i in range(len(recent)-1)):
            assessment["strengths"].append("Improving stability trend in recent runs")
    
    return assessment


def generate_markdown_report(
    summaries: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    assessment: Dict[str, Any],
    output_path: Path
) -> None:
    """Generate a comprehensive markdown report."""
    
    lines = [
        "# RC Burn-in Stability Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Period:** {metrics.get('first_run', 'N/A')} to {metrics.get('last_run', 'N/A')}",
        f"**Total Runs:** {metrics.get('total_runs', 0)}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"**Stability Rating:** {assessment['rating']}",
        f"**Stability Score:** {assessment['score']}/100",
        "",
        f"**Recommendation:** {assessment['recommendation']}",
        "",
    ]
    
    # Concerns and strengths
    if assessment.get("concerns"):
        lines.append("### Concerns")
        lines.append("")
        for concern in assessment["concerns"]:
            lines.append(f"- ⚠️ {concern}")
        lines.append("")
    
    if assessment.get("strengths"):
        lines.append("### Strengths")
        lines.append("")
        for strength in assessment["strengths"]:
            lines.append(f"- ✅ {strength}")
        lines.append("")
    
    # Overall metrics
    lines.extend([
        "---",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Cycles | {metrics.get('total_cycles', 0)} |",
        f"| Successful Cycles | {metrics.get('successful_cycles', 0)} |",
        f"| Failed Cycles | {metrics.get('failed_cycles', 0)} |",
        f"| Overall Pass Rate | {metrics.get('overall_pass_rate', 0):.1f}% |",
        f"| Average Pass Rate | {metrics.get('avg_pass_rate', 0):.1f}% |",
        f"| Total Duration | {metrics.get('duration_stats', {}).get('total_seconds', 0):.1f}s |",
        "",
    ])
    
    # Gate statistics
    lines.extend([
        "---",
        "",
        "## Gate Statistics",
        "",
        "| Gate | Runs | Passes | Failures | Reliability | Avg Duration |",
        "|------|------|--------|----------|-------------|--------------|",
    ])
    
    for gate_name, gate_data in metrics.get("gate_results", {}).items():
        reliability = gate_data.get("reliability", 0)
        avg_duration = gate_data.get("avg_duration")
        duration_str = f"{avg_duration:.2f}s" if avg_duration else "N/A"
        
        lines.append(
            f"| {gate_name} | {gate_data.get('total_runs', 0)} | "
            f"{gate_data.get('total_passes', 0)} | {gate_data.get('total_failures', 0)} | "
            f"{reliability:.1f}% | {duration_str} |"
        )
    
    lines.append("")
    
    # Pass rate trend
    pass_rates = metrics.get("pass_rate_trend", [])
    if pass_rates:
        lines.extend([
            "---",
            "",
            "## Pass Rate Trend",
            "",
            "```",
        ])
        
        # Simple ASCII chart
        max_rate = max(pass_rates) if pass_rates else 100
        min_rate = min(pass_rates) if pass_rates else 0
        range_rate = max_rate - min_rate if max_rate != min_rate else 1
        
        for i, rate in enumerate(pass_rates):
            bar_length = int((rate - min_rate) / range_rate * 40)
            bar = "█" * bar_length
            lines.append(f"Run {i+1:2d}: {bar} {rate:.1f}%")
        
        lines.extend([
            "```",
            "",
        ])
    
    # Individual run details
    if summaries:
        lines.extend([
            "---",
            "",
            "## Individual Run Details",
            "",
        ])
        
        for i, summary in enumerate(summaries[-5:], 1):  # Last 5 runs
            metadata = summary.get("metadata", {})
            summary_data = summary.get("summary", {})
            
            status = "✅ PASS" if summary_data.get("overall_status") == "PASS" else "❌ FAIL"
            
            lines.append(f"### Run {i}: {metadata.get('generated_at', 'Unknown')} - {status}")
            lines.append("")
            lines.append(f"- Mode: {metadata.get('mode', 'Unknown')}")
            lines.append(f"- Cycles: {summary_data.get('cycles_run', 0)}")
            lines.append(f"- Pass Rate: {summary_data.get('cycle_pass_rate', 0):.1f}%")
            lines.append(f"- Duration: {summary_data.get('total_duration_seconds', 0):.1f}s")
            lines.append("")
    
    # Footer
    lines.extend([
        "---",
        "",
        "*Report generated by generate_rc_report.py*",
    ])
    
    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Report written to: {output_path}")


def generate_json_report(
    summaries: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    assessment: Dict[str, Any],
    output_path: Path
) -> None:
    """Generate a JSON report for programmatic access."""
    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "schema": "rc_burn_in_report_v1",
            "source_files": len(summaries),
        },
        "assessment": assessment,
        "metrics": metrics,
        "summaries": summaries,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"JSON report written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate RC Burn-in Stability Report"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("roadmap_ctp/burn_in"),
        help="Input directory containing burn-in summary JSON files"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("docs/RC_BURN_IN_REPORT.md"),
        help="Output markdown report path"
    )
    parser.add_argument(
        "--json-output", "-j",
        type=Path,
        help="Optional JSON output path"
    )
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Aggregate all summaries in input directory"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Only process the latest summary file"
    )
    
    args = parser.parse_args()
    
    # Find summary files
    if not args.input.exists():
        print(f"Error: Input directory does not exist: {args.input}")
        sys.exit(1)
    
    summary_files = find_burn_in_summaries(args.input)
    
    if not summary_files:
        print(f"Error: No burn-in summary files found in {args.input}")
        sys.exit(1)
    
    if args.latest:
        summary_files = [summary_files[-1]]
    
    print(f"Found {len(summary_files)} summary file(s)")
    
    # Load summaries
    summaries = []
    for path in summary_files:
        data = load_json_file(path)
        if data:
            summaries.append(data)
            print(f"  Loaded: {path.name}")
    
    if not summaries:
        print("Error: No valid summary files could be loaded")
        sys.exit(1)
    
    # Calculate metrics
    print("\nCalculating stability metrics...")
    metrics = calculate_stability_metrics(summaries)
    
    # Assess stability
    print("Assessing stability...")
    assessment = assess_stability(metrics)
    
    print(f"\nStability Rating: {assessment['rating']}")
    print(f"Stability Score: {assessment['score']}/100")
    print(f"Recommendation: {assessment['recommendation']}")
    
    # Generate reports
    print(f"\nGenerating markdown report: {args.output}")
    generate_markdown_report(summaries, metrics, assessment, args.output)
    
    if args.json_output:
        print(f"Generating JSON report: {args.json_output}")
        generate_json_report(summaries, metrics, assessment, args.json_output)
    
    print("\nDone!")
    
    # Exit with appropriate code
    if assessment["score"] >= 90:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
