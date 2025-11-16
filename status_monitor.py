
import requests
import time
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict


@dataclass
class StatusUpdate:
    """Represents a service status update."""
    timestamp: str
    product: str
    status: str
    message: str
    incident_id: Optional[str] = None


class OpenAIStatusMonitor:
 
   
    STATUS_PAGE_ID = "kh3m0q7m9g8m"
    BASE_URL = f"https://{STATUS_PAGE_ID}.statuspage.io/api/v2"

    NORMAL_INTERVAL = 60  # 1 minute during normal operation
    INCIDENT_INTERVAL = 15  # 15 seconds when incidents are active
    
    def __init__(self):
        self.seen_incidents: Set[str] = set()
        self.seen_component_states: Dict[str, str] = {}
        self.last_content_hash: Optional[str] = None
        self.active_incidents = False
        
    def _hash_content(self, data: dict) -> str:
        """Generate hash of content for change detection."""
        content_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def _make_request(self, endpoint: str) -> Optional[dict]:
        """Make API request with error handling."""
        try:
            url = f"{self.BASE_URL}/{endpoint}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[ERROR] API request failed: {e}")
            return None
    
    def fetch_summary(self) -> Optional[dict]:
        """Fetch the status page summary (most efficient endpoint)."""
        return self._make_request("summary.json")
    
    def fetch_incidents(self) -> Optional[List[dict]]:
        """Fetch active and recent incidents."""
        data = self._make_request("incidents.json")
        return data.get("incidents", []) if data else None
    
    def fetch_components(self) -> Optional[List[dict]]:
        """Fetch component status (API services)."""
        data = self._make_request("components.json")
        return data.get("components", []) if data else None
    
    def process_components(self, components: List[dict]) -> List[StatusUpdate]:
        """Detect and process component status changes."""
        updates = []
        
        for component in components:
            component_id = component.get("id")
            name = component.get("name", "Unknown Service")
            status = component.get("status", "unknown")
            
            # Skip if operational or if we've seen this state
            if status == "operational":
                # Clear from tracking if it recovered
                self.seen_component_states.pop(component_id, None)
                continue
            
            # Check if this is a new status change
            previous_status = self.seen_component_states.get(component_id)
            if previous_status != status:
                self.seen_component_states[component_id] = status
                
                # Create update notification
                update = StatusUpdate(
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    product=f"OpenAI API - {name}",
                    status=status.replace("_", " ").title(),
                    message=f"Service status changed to: {status.replace('_', ' ')}"
                )
                updates.append(update)
        
        return updates
    
    def process_incidents(self, incidents: List[dict]) -> List[StatusUpdate]:
        """Detect and process new incidents."""
        updates = []
        
        for incident in incidents:
            incident_id = incident.get("id")
            
            # Skip if we've already processed this incident
            if incident_id in self.seen_incidents:
                continue
            
            self.seen_incidents.add(incident_id)
            
            # Extract incident details
            name = incident.get("name", "Unknown Incident")
            status = incident.get("status", "investigating")
            impact = incident.get("impact", "none")
            
            # Get the latest update message
            incident_updates = incident.get("incident_updates", [])
            latest_message = "No details available"
            if incident_updates:
                latest_message = incident_updates[0].get("body", latest_message)
            
            # Get affected components
            affected_components = incident.get("components", [])
            component_names = [c.get("name", "Unknown") for c in affected_components]
            
            if component_names:
                product = f"OpenAI API - {', '.join(component_names)}"
            else:
                product = "OpenAI API - Multiple Services"
            
            # Create update notification
            update = StatusUpdate(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                product=product,
                status=f"{impact.title()} - {status.replace('_', ' ').title()}",
                message=latest_message[:200],  # Truncate long messages
                incident_id=incident_id
            )
            updates.append(update)
        
        return updates
    
    def check_for_updates(self) -> List[StatusUpdate]:
        """Check for any status updates (main monitoring logic)."""
        all_updates = []
        
        # First, check the summary for quick change detection
        summary = self.fetch_summary()
        if not summary:
            return all_updates
        
        # Hash the summary to detect any changes
        current_hash = self._hash_content(summary)
        if current_hash == self.last_content_hash:
            # No changes detected, skip detailed checks
            return all_updates
        
        self.last_content_hash = current_hash
        
        # Changes detected - fetch detailed information
        
        # Check for incidents
        incidents = self.fetch_incidents()
        if incidents:
            # Filter for unresolved incidents
            active = [i for i in incidents if i.get("status") not in ["resolved", "postmortem"]]
            self.active_incidents = len(active) > 0
            
            incident_updates = self.process_incidents(incidents)
            all_updates.extend(incident_updates)
        
        # Check component status
        components = self.fetch_components()
        if components:
            component_updates = self.process_components(components)
            all_updates.extend(component_updates)
        
        return all_updates
    
    def print_update(self, update: StatusUpdate):
        """Print a status update in the required format."""
        print(f"\n[{update.timestamp}] Product: {update.product}")
        print(f"Status: {update.status}")
        if update.message:
            print(f"Details: {update.message}")
        print("-" * 80)
    
    def run(self, duration_seconds: Optional[int] = None):
        """
        Run the monitoring loop.
        
        Args:
            duration_seconds: How long to run (None = run indefinitely)
        """
        print("=" * 80)
        print("OpenAI Status Monitor - Starting")
        print("=" * 80)
        print(f"Monitoring: https://{self.STATUS_PAGE_ID}.statuspage.io")
        print(f"Check interval: {self.NORMAL_INTERVAL}s (normal) / {self.INCIDENT_INTERVAL}s (incident)")
        print("=" * 80)
        
        start_time = time.time()
        
        try:
            while True:
                # Check for updates
                updates = self.check_for_updates()
                
                # Print any new updates
                for update in updates:
                    self.print_update(update)
                
                # Determine sleep interval based on incident status
                interval = self.INCIDENT_INTERVAL if self.active_incidents else self.NORMAL_INTERVAL
                
                # Check if we should stop
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break
                
                # Sleep until next check
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")
            raise


def main():
    """Entry point for the status monitor."""
    monitor = OpenAIStatusMonitor()
    
    monitor.run()


if __name__ == "__main__":
    main()
