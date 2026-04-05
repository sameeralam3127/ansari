"""
Resource health checking module.
"""

from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table


class HealthStatus(str, Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ResourceHealth(BaseModel):
    """Resource health check result."""
    
    resource_name: str
    resource_type: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None


class ResourceChecker:
    """Base class for resource health checking."""
    
    def __init__(self):
        self.console = Console()
    
    def check_resource(self, resource_name: str) -> ResourceHealth:
        """
        Check the health of a resource.
        
        Args:
            resource_name: Name of the resource to check
            
        Returns:
            ResourceHealth object with check results
        """
        # This is a placeholder implementation
        # In a real implementation, this would connect to actual APIs
        
        if "cluster" in resource_name.lower():
            return ResourceHealth(
                resource_name=resource_name,
                resource_type="eks-cluster",
                status=HealthStatus.HEALTHY,
                message="Cluster is running and all nodes are ready",
                details={
                    "nodes": 3,
                    "pods_running": 45,
                    "version": "1.28"
                }
            )
        elif "pod" in resource_name.lower():
            return ResourceHealth(
                resource_name=resource_name,
                resource_type="kubernetes-pod",
                status=HealthStatus.HEALTHY,
                message="Pod is running successfully",
                details={
                    "status": "Running",
                    "restarts": 0,
                    "age": "2d"
                }
            )
        else:
            return ResourceHealth(
                resource_name=resource_name,
                resource_type="unknown",
                status=HealthStatus.UNKNOWN,
                message="Resource type not recognized",
                details={}
            )
    
    def display_health(self, health: ResourceHealth) -> None:
        """
        Display health check results in a formatted table.
        
        Args:
            health: ResourceHealth object to display
        """
        table = Table(title=f"Health Check: {health.resource_name}")
        
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        
        # Status color coding
        status_colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.DEGRADED: "yellow",
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.UNKNOWN: "dim"
        }
        
        status_color = status_colors.get(health.status, "white")
        
        table.add_row("Resource Type", health.resource_type)
        table.add_row("Status", f"[{status_color}]{health.status.value}[/]")
        table.add_row("Message", health.message)
        
        if health.details:
            table.add_row("", "")  # Empty row for spacing
            for key, value in health.details.items():
                table.add_row(f"  {key}", str(value))
        
        self.console.print(table)

# Made with Bob
