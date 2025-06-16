#!/usr/bin/env python3
# extractor2000_improved_fixed_v2.py

"""
Improved version of the experiment runner with:
- Reduced debug file generation
- Ability to skip specific experiments
- Better Delfi progress tracking
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

class ImprovedExperimentRunner:
    def __init__(self):
        self.base_url = "https://solver.planning.domains:5001"
        # Directory for successful results
        self.results_dir = "data_collection_three_domains"
        # Directory for debug/timeout/failed results
        self.debug_dir = "rerun_results_extended_timeout"
        
        # Create directories if they don't exist
        Path(self.results_dir).mkdir(exist_ok=True)
        Path(self.debug_dir).mkdir(exist_ok=True)
        
        # The 4 planners you're testing
        self.planners = ["lama-first", "dual-bfws-ffparser", "delfi", "optic"]
        

        # BLACKLIST: Skip experiments that are proven to fail

        self.blacklist = [
            # BARMAN DOMAIN (16 failures total)
            
            # LAMA-first (1 failure)
            ("lama-first", "barman", "instance-15.pddl"),
            
            # Dual-BFWS-ffparser (4 failures)
            ("dual-bfws-ffparser", "barman", "instance-3.pddl"),
            ("dual-bfws-ffparser", "barman", "instance-7.pddl"),
            ("dual-bfws-ffparser", "barman", "instance-12.pddl"),
            ("dual-bfws-ffparser", "barman", "instance-15.pddl"),
            
            # Optic - Failed on ALL barman instances (8 failures)
            ("optic", "barman", "instance-1.pddl"),
            ("optic", "barman", "instance-2.pddl"),
            ("optic", "barman", "instance-3.pddl"),
            ("optic", "barman", "instance-5.pddl"),
            ("optic", "barman", "instance-7.pddl"),
            ("optic", "barman", "instance-10.pddl"),
            ("optic", "barman", "instance-12.pddl"),
            ("optic", "barman", "instance-15.pddl"),
            
            # Delfi - Failed on ALL barman instances (8 failures)
            ("delfi", "barman", "instance-1.pddl"),
            ("delfi", "barman", "instance-2.pddl"),
            ("delfi", "barman", "instance-3.pddl"),
            ("delfi", "barman", "instance-5.pddl"),
            ("delfi", "barman", "instance-7.pddl"),
            ("delfi", "barman", "instance-10.pddl"),
            ("delfi", "barman", "instance-12.pddl"),
            ("delfi", "barman", "instance-15.pddl"),
            
            # BLOCKSWORLD DOMAIN (4 failures total)
            
            # Optic (1 failure)
            ("optic", "blocksworld", "problema_08_dificil.pddl"),
            
            # Delfi (3 failures)
            ("delfi", "blocksworld", "problema_05_medio.pddl"),
            ("delfi", "blocksworld", "problema_06_medio.pddl"),
            ("delfi", "blocksworld", "problema_09_dificil.pddl"),
            
            # LOGISTICS DOMAIN (0 failures)
            # All planners succeeded on all logistics problems
            
            # TOTAL: 25 failures
            # Summary by planner:
            # - LAMA-first: 1 failure
            # - Dual-BFWS-ffparser: 4 failures  
            # - Optic: 9 failures (8 barman + 1 blocksworld)
            # - Delfi: 11 failures (8 barman + 3 blocksworld)
        ]

        
        # Track last debug state to avoid duplicate saves
        self.last_debug_state = {}
        
       # FOCUSED TIMEOUTS: Only for promising experiments
        self.extended_timeouts = {
            "lama-first": {
                # Blocksworld - Good chance of success
                "dificil": 3600,      # 1 hour
                
                # Logistics - Reasonable
                "LOGISTICS-5": 3600,  # 1 hour
                "LOGISTICS-7": 3600,  # 1 hour
                "LOGISTICS-8": 3600,  # 1 hour
                "LOGISTICS-9": 3600,  # 1 hour
                
                # Barman - Only easy instances
                "instance-3": 3600,   # 1 hour
                "instance-5": 3600,   # 1 hour
                
                # Keep defaults for others
                "facil": 3600,
                "medio": 3600,
                "default": 3600       # 1 hour default
            },
            
            "dual-bfws-ffparser": {
                # Blocksworld - Very likely to succeed
                "dificil": 3600,      # 1 hour
                
                # Logistics - Should handle well
                "LOGISTICS-5": 3600,  # 1 hour
                "LOGISTICS-7": 3600,  # 1 hour
                "LOGISTICS-8": 3600,  # 1 hour
                "LOGISTICS-9": 3600,  # 1 hour
                
                # Barman - Only very easy ones
                "instance-1": 3600,
                "instance-2": 3600,
                "instance-5": 3600,   # 1 hour
                
                # Keep defaults
                "facil": 3600,
                "medio": 3600,
                "default": 3600       # 1 hour default
            },
            
            "delfi": {
                # Blocksworld - Give extra time for preprocessing
                "dificil": 10800,     # 3 hours (significantly increased)
                
                # Logistics - Reasonable with preprocessing
                "LOGISTICS-5": 7200,  # 2 hours
                "LOGISTICS-7": 9000,  # 2.5 hours
                "LOGISTICS-8": 10800, # 3 hours
                "LOGISTICS-9": 10800, # 3 hours
                
                # Barman - Only easy ones
                "instance-3": 7200,   # 2 hours
                "instance-5": 9000,   # 2.5 hours
                
                # Keep defaults
                "facil": 5400,        # 1.5 hours
                "medio": 7200,        # 2 hours
                "default": 7200       # 2 hours default
            },
            
            "optic": {
                # Only attempt easier problems with moderate timeouts
                "facil": 720,         # 12 minutes
                "medio": 900,         # 15 minutes
                "LOGISTICS-4": 840,   # 14 minutes
                "LOGISTICS-5": 960,   # 16 minutes
                "LOGISTICS-7": 1080,  # 18 minutes
                "instance-1": 720,    # 12 minutes
                "instance-2": 840,    # 14 minutes
                "default": 840        # 14 minutes default
            }
        }
   
        
        self.domain_actions = {
            "blocksworld": ['pick-up', 'put-down', 'stack', 'unstack'],
            "barman": [
                'grasp', 'leave', 'fill-shot', 'refill-shot', 'empty-shot',
                'clean-shot', 'pour-shot-to-clean-shaker', 'pour-shot-to-used-shaker',
                'empty-shaker', 'clean-shaker', 'shake', 'pour-shaker-to-shot'
            ],
            "logistics": [
                'load-truck', 'load-airplane', 'unload-truck', 'unload-airplane',
                'drive-truck', 'fly-airplane'
            ]
        }
        
        self.domains = {}
        self._load_domains()
        self._discover_problems()
    
    def _load_domains(self):
        """Load domain files with correct names"""
        domain_configs = [
            ("blocksworld", "blocksworld_files/blocksworld_domain.pddl"),
            ("barman", "barman_files/domain.pddl"),
            ("logistics", "logistics_files/probLOGISTICS_domain.pddl")
        ]
        
        for domain_name, path in domain_configs:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        self.domains[domain_name] = f.read()
                    print(f"✓ Loaded {domain_name} domain from {path}")
                except Exception as e:
                    print(f"✗ Failed to load {domain_name} from {path}: {e}")
            else:
                print(f"✗ {domain_name} domain file not found at: {path}")
    
    def _discover_problems(self):
        """Discover all problem files for each domain"""
        self.all_problems = []
        
        problem_patterns = {
            "blocksworld": ("blocksworld_files", "problema_*.pddl"),
            "barman": ("barman_files", "instance-*.pddl"),
            "logistics": ("logistics_files", "probLOGISTICS-*.pddl")
        }
        
        for domain, (directory, pattern) in problem_patterns.items():
            if os.path.exists(directory):
                problem_files = sorted(glob.glob(os.path.join(directory, pattern)))
                for problem_path in problem_files:
                    problem_name = os.path.basename(problem_path)
                    self.all_problems.append((domain, problem_name, directory))
                print(f"Found {len(problem_files)} problems for {domain}")
        
        print(f"Total problems discovered: {len(self.all_problems)}")
    
    def is_blacklisted(self, planner, domain, problem):
        """Check if an experiment is in the blacklist"""
        return (planner, domain, problem) in self.blacklist
    
    def check_existing_result(self, domain, planner, problem):
        """Check if a successful result already exists"""
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
        """Get appropriate timeout for the problem"""
        timeouts = self.extended_timeouts.get(planner, {})
        
        # Check specific problem patterns
        for key in timeouts:
            if key in problem:
                return timeouts[key]
        
        # Return default timeout
        return timeouts.get('default', 1800)
    
    def monitor_delfi_progress(self, stdout_text):
        """Extract Delfi progress information"""
        progress_info = {}
        
        # Check initialization phases
        if "Done initializing merge-and-shrink heuristic" in stdout_text:
            match = re.search(r"Done initializing merge-and-shrink heuristic \[(\d+\.\d+)s\]", stdout_text)
            if match:
                progress_info['initialization_time'] = float(match.group(1))
        
        # Check which planner Delfi selected
        if "Chose" in stdout_text:
            match = re.search(r"Chose ([^\n]+)", stdout_text)
            if match:
                progress_info['selected_config'] = match.group(1).strip()
        
        # Check search progress
        if "evaluated" in stdout_text:
            matches = re.findall(r"\[g=(\d+), (\d+) evaluated, (\d+) expanded, t=([\d.]+)s", stdout_text)
            if matches:
                last_match = matches[-1]
                progress_info['g_value'] = int(last_match[0])
                progress_info['evaluated'] = int(last_match[1])
                progress_info['expanded'] = int(last_match[2])
                progress_info['search_time'] = float(last_match[3])
        
        # Check f-value progression
        f_values = re.findall(r"f = (\d+)", stdout_text)
        if f_values:
            progress_info['current_f'] = int(f_values[-1])
            progress_info['f_progression'] = [int(f) for f in f_values]
        
        # Check heuristic value improvements
        h_improvements = re.findall(r"New best heuristic value[^:]+: (\d+)", stdout_text)
        if h_improvements:
            progress_info['h_progression'] = [int(h) for h in h_improvements]
        
        # Check for timeout/signal
        if "caught signal" in stdout_text:
            progress_info['terminated'] = "signal"
        elif "timeout" in stdout_text.lower():
            progress_info['terminated'] = "timeout"
        
        return progress_info
    
    def should_save_debug(self, planner, domain, problem, progress_info):
        """Determine if debug info should be saved based on state changes"""
        key = f"{planner}_{domain}_{problem}"
        
        # Always save first debug
        if key not in self.last_debug_state:
            self.last_debug_state[key] = progress_info
            return True
        
        last_state = self.last_debug_state[key]
        
        # For Delfi, check if meaningful progress has been made
        if planner == "delfi":
            # Save if evaluated states changed significantly (more than 1000)
            if progress_info.get('evaluated', 0) - last_state.get('evaluated', 0) > 1000:
                self.last_debug_state[key] = progress_info
                return True
            
            # Save if f-value changed
            if progress_info.get('current_f') != last_state.get('current_f'):
                self.last_debug_state[key] = progress_info
                return True
        
        # For other planners, save every 5 minutes
        return False
    
    def run_experiment_with_extended_timeout(self, planner, problem, domain, problem_dir):
        """Run experiment with reduced debug saving"""
        
        # Check if blacklisted
        if self.is_blacklisted(planner, domain, problem):
            print(f"⚠️  SKIPPED (blacklisted): {domain}/{problem} with {planner}")
            return {"solved": False, "error": "Blacklisted", "skipped": True}
        
        # Check if already solved
        exists, existing_data = self.check_existing_result(domain, planner, problem)
        if exists:
            print(f"✓ Already solved: {domain}/{problem} with {planner} (length: {existing_data['plan_length']})")
            return existing_data
        
        # Get domain and problem content
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
        print(f"Running: {planner} on {domain}/{problem}")
        print(f"Timeout: {timeout} seconds ({timeout/60:.1f} minutes)")
        if planner == "delfi":
            print("Note: Delfi includes ~25s preprocessing overhead")
        print('='*70)
        
        # Map planner names to solver.planning.domains format if needed
        solver_planner = planner
        url = f"{self.base_url}/package/{solver_planner}/solve"
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
            "raw": None,
            "error": None,
            "progress_info": {}
        }
        
        try:
            start = time.time()
            print("→ Sending request to planner...", end='', flush=True)
            response = requests.post(url, json=data, verify=False, timeout=60)
            
            if response.status_code != 200:
                result_data["error"] = f"HTTP {response.status_code}"
                result_data["time"] = time.time() - start
                print(f" FAILED (HTTP {response.status_code})")
                
                # Save failed result to debug directory
                self._save_failed_result(domain, planner, problem, result_data)
                return result_data
            
            initial = response.json()
            if 'result' not in initial:
                result_data["error"] = "No result URL"
                result_data["time"] = time.time() - start
                print(" FAILED (No URL)")
                
                # Save failed result to debug directory
                self._save_failed_result(domain, planner, problem, result_data)
                return result_data
            
            result_url = self.base_url + initial['result']
            print(" OK")
            print(f"→ Polling for results (timeout: {timeout}s)...", end='', flush=True)
            
            # Poll with reduced debug saving
            last_progress = time.time()
            last_debug_save = time.time()
            poll_responses = []
            debug_save_count = 0
            max_debug_saves = 5  # Limit total debug saves per experiment
            
            while time.time() - start < timeout:
                try:
                    resp = requests.get(result_url, verify=False, timeout=10)
                    if resp.status_code == 200:
                        resp_data = resp.json()
                        
                        # Store response for debugging
                        poll_responses.append({
                            "time_elapsed": time.time() - start,
                            "status": resp_data.get('status'),
                            "has_result": 'result' in resp_data
                        })
                        
                        if 'status' in resp_data and resp_data['status'] == 'ok':
                            result_data["time"] = time.time() - start
                            result_data["raw"] = resp_data
                            
                            # Extract progress info for monitoring
                            if 'result' in resp_data and 'stdout' in resp_data.get('result', {}):
                                result_data["progress_info"] = self.monitor_delfi_progress(resp_data['result']['stdout'])
                            
                            if 'result' in resp_data:
                                res = resp_data['result']
                                plan = self.extract_plan(res, planner, domain)
                                
                                if plan and len(plan) > 0:
                                    result_data["solved"] = True
                                    result_data["plan"] = plan
                                    result_data["plan_length"] = len(plan)
                                    print(f"\n✓ SOLVED! Found plan with {len(plan)} actions in {result_data['time']:.1f}s")
                                    
                                    # Save successful result to main results directory
                                    filename = f"{domain}_{planner}_{problem.replace('.pddl', '')}.json"
                                    filepath = os.path.join(self.results_dir, filename)
                                    with open(filepath, 'w') as f:
                                        json.dump(result_data, f, indent=2)
                                    
                                    return result_data
                                else:
                                    # No plan found yet - show progress
                                    if time.time() - last_progress > 30:
                                        elapsed = time.time() - start
                                        progress_msg = f"\n  Still running... ({elapsed:.0f}s elapsed"
                                        
                                        # Add progress info
                                        progress_info = result_data.get("progress_info", {})
                                        if 'evaluated' in progress_info:
                                            progress_msg += f", {progress_info['evaluated']} states evaluated"
                                        if 'current_f' in progress_info:
                                            progress_msg += f", f={progress_info['current_f']}"
                                        
                                        print(progress_msg + ")", end='', flush=True)
                                        last_progress = time.time()
                                        
                                        # Only save debug if state changed significantly
                                        if (planner == "delfi" and 
                                            debug_save_count < max_debug_saves and
                                            self.should_save_debug(planner, domain, problem, progress_info)):
                                            self._save_minimal_debug_info(domain, planner, problem, start, progress_info)
                                            debug_save_count += 1
                                    
                        elif 'status' in resp_data and resp_data['status'] in ['error', 'failed']:
                            result_data["error"] = "Planning failed"
                            result_data["time"] = time.time() - start
                            print(f"\n✗ FAILED: Planning error after {result_data['time']:.1f}s")
                            
                            # Save failed result to debug directory
                            self._save_failed_result(domain, planner, problem, result_data)
                            return result_data
                    
                    time.sleep(0.5)
                    
                except Exception as e:
                    time.sleep(0.5)
            
            # Timeout - save minimal debug info
            result_data["error"] = "Extended timeout reached"
            result_data["time"] = time.time() - start
            
            self._save_timeout_debug(domain, planner, problem, timeout, result_data, poll_responses[-10:], result_url)
            
            print(f"\n✗ TIMEOUT: No solution found within {timeout}s")
            if planner == "delfi" and result_data.get("progress_info"):
                info = result_data["progress_info"]
                if 'initialization_time' in info:
                    print(f"   Delfi initialization took: {info['initialization_time']:.1f}s")
                if 'evaluated' in info:
                    print(f"   States evaluated before timeout: {info['evaluated']}")
            
            print(f"   Debug info saved to: {self.debug_dir}/")
            
            return result_data
            
        except Exception as e:
            result_data["error"] = str(e)[:100]
            result_data["time"] = time.time() - start
            print(f"\n✗ ERROR: {str(e)[:50]}")
            
            # Save error result to debug directory
            self._save_failed_result(domain, planner, problem, result_data)
            return result_data
    
    def _save_minimal_debug_info(self, domain, planner, problem, start_time, progress_info):
        """Save minimal debug information"""
        debug_data = {
            "domain": domain,
            "planner": planner,
            "problem": problem,
            "timestamp": datetime.now().isoformat(),
            "elapsed_time": time.time() - start_time,
            "progress": progress_info
        }
        
        filename = f"DEBUG_{domain}_{planner}_{problem.replace('.pddl', '')}_{int(time.time())}.json"
        filepath = os.path.join(self.debug_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(debug_data, f, indent=2)
    
    def _save_failed_result(self, domain, planner, problem, result_data):
        """Save failed result to debug directory"""
        filename = f"{domain}_{planner}_{problem.replace('.pddl', '')}_FAILED.json"
        filepath = os.path.join(self.debug_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(result_data, f, indent=2)
    
    def _save_timeout_debug(self, domain, planner, problem, timeout, result_data, last_polls, result_url):
        """Save comprehensive timeout debug information"""
        debug_data = {
            "domain": domain,
            "planner": planner,
            "problem": problem,
            "timestamp": datetime.now().isoformat(),
            "timeout_used": timeout,
            "total_time": result_data["time"],
            "error": "TIMEOUT",
            "last_poll_responses": last_polls,
            "result_url": result_url,
            "final_progress": result_data.get("progress_info", {}),
            "notes": f"Planner did not complete within {timeout} seconds"
        }
        
        filename = f"TIMEOUT_{domain}_{planner}_{problem.replace('.pddl', '')}_{int(time.time())}.json"
        filepath = os.path.join(self.debug_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(debug_data, f, indent=2)
    
    def extract_plan(self, result, planner, domain):
        """Extract plan from result"""
        sources = []
        
        if 'output' in result:
            if isinstance(result['output'], dict):
                if 'plan' in result['output']:
                    sources.append(result['output']['plan'])
                if 'sas_plan' in result['output']:
                    sources.append(result['output']['sas_plan'])
                    
        if 'stdout' in result:
            sources.append(result['stdout'])
        
        for source in sources:
            if source:
                plan = self._parse_plan_text(str(source), domain, planner)
                if plan:
                    return plan
        
        return []
    
    def _parse_plan_text(self, text, domain, planner):
        """Parse plan text with improved Delfi support"""
        plan = []
        valid_actions = self.domain_actions.get(domain, [])
        
        # Check for timeout/signal
        if 'caught signal' in text or 'exiting' in text:
            return []
        
        # Special handling for Delfi/Fast Downward format
        if planner == "delfi":
            # Check if Delfi/Fast Downward found a solution
            if 'Solution found!' in text or 'Plan length:' in text:
                lines = text.split('\n')
                in_plan_section = False
                
                for i, line in enumerate(lines):
                    # Look for plan section markers
                    if 'Solution found!' in line or 'Plan length:' in line:
                        in_plan_section = True
                        continue
                    
                    # Also check for actual plan start (sometimes after cost info)
                    if 'Plan cost:' in line or 'Actual search time:' in line:
                        # Plan usually starts after these lines
                        in_plan_section = True
                        continue
                    
                    if in_plan_section:
                        line = line.strip()
                        
                        # Skip empty lines and metadata
                        if not line or line.startswith(';') or ':' in line:
                            continue
                        
                        # Check if line looks like an action
                        if line.startswith('(') and line.endswith(')'):
                            # Parse the action
                            action_text = line[1:-1].strip().lower()
                            action_parts = action_text.split()
                            
                            if action_parts and action_parts[0] in valid_actions:
                                plan.append(f"({action_text})")
                        elif any(action in line.lower() for action in valid_actions):
                            # Try to extract action from line
                            line_lower = line.lower()
                            for action in valid_actions:
                                if action in line_lower:
                                    # Extract the full action with parameters
                                    match = re.search(rf'\b{action}\s+[^()]+', line_lower)
                                    if match:
                                        action_text = match.group(0).strip()
                                        plan.append(f"({action_text})")
                                        break
        
        # If no plan found with Delfi format, try generic patterns
        if not plan:
            patterns = [
                r'^\s*\(([^)]+)\)\s*$',  # Standard (action param1 param2)
                r'^\s*[\d.]+:\s*\(([^)]+)\)(?:\s*\[[\d.]+\])?',  # Temporal: 0.000: (action) [duration]
                r'^\s*\d+:\s*\(([^)]+)\)',  # Numbered: 1: (action)
                r'^\s*step\s+\d+:\s*([A-Z\-]+(?:\s+[A-Z0-9\-]+)*)',  # Step format
            ]
            
            for line in text.split('\n'):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                    
                for pattern in patterns:
                    match = re.match(pattern, line, re.IGNORECASE)
                    if match:
                        action_text = match.group(1).strip().lower()
                        action_parts = action_text.split()
                        
                        if action_parts and action_parts[0] in valid_actions:
                            if not action_text.startswith('('):
                                action_text = f"({action_text})"
                            plan.append(action_text)
                            break
        
        return plan
    
    def run_all_experiments(self):
        """Run all experiments (all planners × all problems)"""
        total_experiments = len(self.planners) * len(self.all_problems)
        print(f"\nTotal possible experiments: {total_experiments}")
        print(f"Planners: {', '.join(self.planners)}")
        print(f"Domains: blocksworld, barman, logistics")
        print(f"\nSuccessful results will be saved to: {self.results_dir}/")
        print(f"Debug/failed results will be saved to: {self.debug_dir}/")
        
        # Count blacklisted experiments
        blacklisted_count = 0
        for planner in self.planners:
            for domain, problem, _ in self.all_problems:
                if self.is_blacklisted(planner, domain, problem):
                    blacklisted_count += 1
        
        print(f"\nBlacklisted experiments: {blacklisted_count}")
        
        # Count existing results
        existing_count = 0
        to_run = []
        
        for planner in self.planners:
            for domain, problem, problem_dir in self.all_problems:
                if self.is_blacklisted(planner, domain, problem):
                    continue
                    
                exists, _ = self.check_existing_result(domain, planner, problem)
                if exists:
                    existing_count += 1
                else:
                    to_run.append((planner, domain, problem, problem_dir))
        
        print(f"Existing successful results: {existing_count}")
        print(f"Experiments to run: {len(to_run)}")
        
        if len(to_run) == 0:
            print("\n✓ All non-blacklisted experiments completed!")
            return {"solved": existing_count, "failed": 0, "timeout": 0, "skipped": blacklisted_count}
        
        # Run experiments
        stats = {"solved": 0, "failed": 0, "timeout": 0, "skipped": blacklisted_count}
        
        for i, (planner, domain, problem, problem_dir) in enumerate(to_run, 1):
            print(f"\n[{i}/{len(to_run)}] {planner} on {domain}/{problem}")
            
            result = self.run_experiment_with_extended_timeout(planner, problem, domain, problem_dir)
            
            if result.get("skipped", False):
                # Already counted in blacklisted_count
                pass
            elif result.get("solved", False):
                stats["solved"] += 1
                print(f"   → Saved to: {self.results_dir}/{domain}_{planner}_{problem.replace('.pddl', '')}.json")
            elif "timeout" in str(result.get("error", "")).lower():
                stats["timeout"] += 1
                print(f"   → Timeout info saved to: {self.debug_dir}/")
            else:
                stats["failed"] += 1
                print(f"   → Failed info saved to: {self.debug_dir}/")
            
            # Small delay between experiments
            time.sleep(2)
        
        # Print summary
        print(f"\n\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Total experiments: {total_experiments}")
        print(f"Blacklisted: {blacklisted_count}")
        print(f"Already solved: {existing_count}")
        print(f"Experiments run: {len(to_run)}")
        print(f"Newly solved: {stats['solved']}")
        print(f"Failed: {stats['failed']}")
        print(f"Timeout: {stats['timeout']}")
        print(f"Total solved: {existing_count + stats['solved']}")
        effective_total = total_experiments - blacklisted_count
        print(f"Success rate: {((existing_count + stats['solved']) / effective_total * 100):.1f}% (excluding blacklisted)")
        
        # Save summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_possible": total_experiments,
            "blacklisted": blacklisted_count,
            "existing_successful": existing_count,
            "experiments_run": len(to_run),
            "stats": stats,
            "total_solved": existing_count + stats["solved"],
            "success_rate": (existing_count + stats["solved"]) / effective_total * 100,
            "planners": self.planners,
            "domains": ["blocksworld", "barman", "logistics"],
            "results_directory": self.results_dir,
            "debug_directory": self.debug_dir,
            "blacklist": self.blacklist
        }
        
        with open(os.path.join(self.debug_dir, "run_summary.json"), 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\nSuccessful results saved to: {os.path.abspath(self.results_dir)}/")
        print(f"Debug/failed results saved to: {os.path.abspath(self.debug_dir)}/")
        
        return stats

def main():
    print("IMPROVED COMPREHENSIVE EXPERIMENT RUNNER v2")
    print("With blacklist support and reduced debug file generation")
    print("="*70)
    
    runner = ImprovedExperimentRunner()
    
    print("\nOptions:")
    print("1. Run all missing experiments")
    print("2. Show status only")
    print("3. Show blacklisted experiments")
    print("4. Exit")
    
    choice = input("\nChoice (1-4): ").strip()
    
    if choice == "1":
        runner.run_all_experiments()
    elif choice == "2":
        # Just show status
        existing_count = 0
        missing_count = 0
        blacklisted_count = 0
        by_planner = {p: {"solved": 0, "missing": 0, "blacklisted": 0} for p in runner.planners}
        
        for planner in runner.planners:
            for domain, problem, _ in runner.all_problems:
                if runner.is_blacklisted(planner, domain, problem):
                    blacklisted_count += 1
                    by_planner[planner]["blacklisted"] += 1
                else:
                    exists, _ = runner.check_existing_result(domain, planner, problem)
                    if exists:
                        existing_count += 1
                        by_planner[planner]["solved"] += 1
                    else:
                        missing_count += 1
                        by_planner[planner]["missing"] += 1
        
        print(f"\nOverall Status:")
        print(f"  Total experiments: {len(runner.planners) * len(runner.all_problems)}")
        print(f"  Blacklisted: {blacklisted_count}")
        print(f"  Completed: {existing_count}")
        print(f"  Missing: {missing_count}")
        
        print(f"\nBy Planner:")
        for planner, stats in by_planner.items():
            total = stats["solved"] + stats["missing"] + stats["blacklisted"]
            effective_total = stats["solved"] + stats["missing"]
            rate = (stats["solved"] / effective_total * 100) if effective_total > 0 else 0
            print(f"  {planner}: {stats['solved']}/{effective_total} ({rate:.1f}%) [{stats['blacklisted']} blacklisted]")
    
    elif choice == "3":
        # Show blacklisted experiments
        print("\nBlacklisted experiments:")
        for planner, domain, problem in runner.blacklist:
            print(f"  - {planner} on {domain}/{problem}")
        print(f"\nTotal: {len(runner.blacklist)} experiments")

if __name__ == "__main__":
    main()