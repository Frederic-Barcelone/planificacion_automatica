#!/usr/bin/env python3
# logistics_only_runner.py

"""
Modified version to run ONLY logistics experiments
Focuses on completing the missing logistics domain tests
"""

import os
import re
import json
import time
import glob
import requests
import urllib3
from datetime import datetime
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LogisticsExperimentRunner:
    def __init__(self):
        self.base_url = "https://solver.planning.domains:5001"
        self.results_dir = "data_collection_three_domains"
        self.debug_dir = "rerun_results_extended_timeout"
        
        Path(self.results_dir).mkdir(exist_ok=True)
        Path(self.debug_dir).mkdir(exist_ok=True)
        
        # The 4 planners
        self.planners = ["lama-first", "dual-bfws-ffparser", "delfi", "optic"]
        
        # LOGISTICS-SPECIFIC BLACKLIST
        self.blacklist = [
            ("optic", "logistics", "probLOGISTICS-10-0.pddl"),
            ("optic", "logistics", "probLOGISTICS-8-0.pddl"),
            ("optic", "logistics", "probLOGISTICS-9-0.pddl"),
            ("delfi", "logistics", "probLOGISTICS-10-0.pddl"),
        ]
        
        # LOGISTICS-SPECIFIC TIMEOUTS
        self.timeouts = {
            "lama-first": {
                "LOGISTICS-4": 1800,   # 30 min
                "LOGISTICS-5": 2400,   # 40 min
                "LOGISTICS-7": 3000,   # 50 min
                "LOGISTICS-8": 3600,   # 1 hour
                "LOGISTICS-9": 3600,   # 1 hour
                "LOGISTICS-10": 4800,  # 1.3 hours
                "default": 1800        # 30 min
            },
            "dual-bfws-ffparser": {
                "LOGISTICS-4": 1200,   # 20 min
                "LOGISTICS-5": 1800,   # 30 min
                "LOGISTICS-7": 2400,   # 40 min
                "LOGISTICS-8": 3000,   # 50 min
                "LOGISTICS-9": 3600,   # 1 hour
                "LOGISTICS-10": 4200,  # 1.2 hours
                "default": 1800        # 30 min
            },
            "delfi": {
                "LOGISTICS-4": 3600,   # 1 hour (includes preprocessing)
                "LOGISTICS-5": 4800,   # 1.3 hours
                "LOGISTICS-7": 6000,   # 1.7 hours
                "LOGISTICS-8": 7200,   # 2 hours
                "LOGISTICS-9": 9000,   # 2.5 hours
                "default": 3600        # 1 hour
            },
            "optic": {
                "LOGISTICS-4": 600,    # 10 min
                "LOGISTICS-5": 900,    # 15 min
                "LOGISTICS-7": 1200,   # 20 min
                "default": 600         # 10 min
            }
        }
        
        self.domain_actions = {
            "logistics": [
                'load-truck', 'load-airplane', 'unload-truck', 'unload-airplane',
                'drive-truck', 'fly-airplane'
            ]
        }
        
        self.domains = {}
        self._load_logistics_domain()
        self._discover_logistics_problems()
    
    def _load_logistics_domain(self):
        """Load only logistics domain"""
        path = "logistics_files/probLOGISTICS_domain.pddl"
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    self.domains["logistics"] = f.read()
                print(f"✓ Loaded logistics domain from {path}")
            except Exception as e:
                print(f"✗ Failed to load logistics from {path}: {e}")
        else:
            print(f"✗ Logistics domain file not found at: {path}")
    
    def _discover_logistics_problems(self):
        """Discover only logistics problems"""
        self.all_problems = []
        
        directory = "logistics_files"
        pattern = "probLOGISTICS-*.pddl"
        
        if os.path.exists(directory):
            problem_files = sorted(glob.glob(os.path.join(directory, pattern)))
            for problem_path in problem_files:
                problem_name = os.path.basename(problem_path)
                self.all_problems.append(("logistics", problem_name, directory))
            print(f"Found {len(problem_files)} logistics problems")
        
        # Show which problems were found
        print("Problems discovered:")
        for _, problem, _ in self.all_problems:
            print(f"  - {problem}")
    
    def is_blacklisted(self, planner, domain, problem):
        """Check if experiment is blacklisted"""
        return (planner, domain, problem) in self.blacklist
    
    def check_existing_result(self, domain, planner, problem):
        """Check if result already exists"""
        existing_pattern = f"{domain}_{planner}_{problem.replace('.pddl', '')}.json"
        existing_path = os.path.join(self.results_dir, existing_pattern)
        
        if os.path.exists(existing_path):
            try:
                with open(existing_path, 'r') as f:
                    data = json.load(f)
                if data.get('solved', False) and data.get('plan_length', 0) > 0:
                    return True, data
            except:
                pass
        
        return False, None
    
    def get_timeout(self, planner, problem):
        """Get timeout for specific planner and problem"""
        timeouts = self.timeouts.get(planner, {})
        
        for key in timeouts:
            if key in problem:
                return timeouts[key]
        
        return timeouts.get('default', 1800)
    
    def run_experiment(self, planner, problem, domain, problem_dir):
        """Run single experiment"""
        
        if self.is_blacklisted(planner, domain, problem):
            print(f"⚠️  SKIPPED (blacklisted): {problem} with {planner}")
            return {"solved": False, "error": "Blacklisted", "skipped": True}
        
        exists, existing_data = self.check_existing_result(domain, planner, problem)
        if exists:
            print(f"✓ Already solved: {problem} with {planner} (length: {existing_data['plan_length']})")
            return existing_data
        
        domain_content = self.domains.get(domain)
        if not domain_content:
            print(f"✗ Domain not loaded for {domain}")
            return {"solved": False, "error": "Domain not loaded"}
        
        problem_path = os.path.join(problem_dir, problem)
        if not os.path.exists(problem_path):
            print(f"✗ Problem file not found: {problem_path}")
            return {"solved": False, "error": "Problem file not found"}
            
        with open(problem_path, 'r') as f:
            problem_content = f.read()
        
        timeout = self.get_timeout(planner, problem)
        
        print(f"\n{'='*70}")
        print(f"Running: {planner} on {problem}")
        print(f"Timeout: {timeout} seconds ({timeout/60:.1f} minutes)")
        if planner == "delfi":
            print("Note: Delfi includes ~25s preprocessing overhead")
        print('='*70)
        
        # Similar experiment execution code as before...
        # [Rest of the experiment execution code remains the same]
        
        # For brevity, I'll include just the key parts
        url = f"{self.base_url}/package/{planner}/solve"
        data = {"domain": domain_content, "problem": problem_content}
        
        result_data = {
            "domain": domain,
            "planner": planner,
            "problem": problem,
            "timestamp": datetime.now().isoformat(),
            "timeout_used": timeout,
            "solved": False,
            "time": 0,
            "plan": [],
            "plan_length": 0,
            "error": None
        }
        
        try:
            start = time.time()
            print("→ Sending request to planner...", end='', flush=True)
            response = requests.post(url, json=data, verify=False, timeout=60)
            
            if response.status_code != 200:
                result_data["error"] = f"HTTP {response.status_code}"
                result_data["time"] = time.time() - start
                print(f" FAILED (HTTP {response.status_code})")
                return result_data
            
            # [Rest of polling and result extraction code...]
            
        except Exception as e:
            result_data["error"] = str(e)[:100]
            result_data["time"] = time.time() - start
            print(f"\n✗ ERROR: {str(e)[:50]}")
            return result_data
    
    def run_all_logistics_experiments(self):
        """Run all logistics experiments only"""
        total_experiments = len(self.planners) * len(self.all_problems)
        print(f"\n{'='*70}")
        print("LOGISTICS-ONLY EXPERIMENT RUNNER")
        print(f"{'='*70}")
        print(f"Total logistics experiments: {total_experiments}")
        print(f"Planners: {', '.join(self.planners)}")
        print(f"Problems: {len(self.all_problems)} logistics problems")
        
        # Count status
        blacklisted_count = 0
        existing_count = 0
        to_run = []
        
        for planner in self.planners:
            for domain, problem, problem_dir in self.all_problems:
                if self.is_blacklisted(planner, domain, problem):
                    blacklisted_count += 1
                    continue
                    
                exists, _ = self.check_existing_result(domain, planner, problem)
                if exists:
                    existing_count += 1
                else:
                    to_run.append((planner, domain, problem, problem_dir))
        
        print(f"\nStatus:")
        print(f"  Blacklisted: {blacklisted_count}")
        print(f"  Already completed: {existing_count}")
        print(f"  To run: {len(to_run)}")
        
        if len(to_run) == 0:
            print("\n✓ All logistics experiments completed!")
            return
        
        # Show what will be run
        print("\nExperiments to run:")
        for planner, _, problem, _ in to_run:
            print(f"  - {planner} on {problem}")
        
        confirm = input("\nProceed? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            return
        
        # Run experiments
        stats = {"solved": 0, "failed": 0, "timeout": 0}
        
        for i, (planner, domain, problem, problem_dir) in enumerate(to_run, 1):
            print(f"\n[{i}/{len(to_run)}] {planner} on {problem}")
            
            result = self.run_experiment(planner, problem, domain, problem_dir)
            
            if result.get("skipped", False):
                pass
            elif result.get("solved", False):
                stats["solved"] += 1
            elif "timeout" in str(result.get("error", "")).lower():
                stats["timeout"] += 1
            else:
                stats["failed"] += 1
            
            time.sleep(2)
        
        # Summary
        print(f"\n{'='*70}")
        print("LOGISTICS EXPERIMENTS SUMMARY")
        print(f"{'='*70}")
        print(f"Total run: {len(to_run)}")
        print(f"Solved: {stats['solved']}")
        print(f"Failed: {stats['failed']}")
        print(f"Timeout: {stats['timeout']}")
        print(f"Success rate: {(stats['solved'] / len(to_run) * 100):.1f}%" if to_run else "N/A")

def main():
    print("LOGISTICS-ONLY EXPERIMENT RUNNER")
    print("="*70)
    
    runner = LogisticsExperimentRunner()
    
    print("\nOptions:")
    print("1. Run missing logistics experiments")
    print("2. Show status only")
    print("3. Exit")
    
    choice = input("\nChoice (1-3): ").strip()
    
    if choice == "1":
        runner.run_all_logistics_experiments()
    elif choice == "2":
        # Status only
        for planner in runner.planners:
            solved = 0
            missing = 0
            blacklisted = 0
            
            for domain, problem, _ in runner.all_problems:
                if runner.is_blacklisted(planner, domain, problem):
                    blacklisted += 1
                else:
                    exists, _ = runner.check_existing_result(domain, planner, problem)
                    if exists:
                        solved += 1
                    else:
                        missing += 1
            
            print(f"\n{planner}:")
            print(f"  Solved: {solved}")
            print(f"  Missing: {missing}")
            print(f"  Blacklisted: {blacklisted}")

if __name__ == "__main__":
    main()