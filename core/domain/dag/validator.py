from typing import List, Dict, Set
from uuid import UUID
from core.domain.tasks.entities import TaskDependency

class DAGCycleError(Exception):
    pass

class DAGDuplicateError(Exception):
    pass

class DAGSelfDependencyError(Exception):
    pass

class DAGValidator:
    @staticmethod
    def validate_new_dependency(
        new_dep: TaskDependency, 
        existing_deps: List[TaskDependency]
    ) -> None:
        if new_dep.task_id == new_dep.depends_on_task_id:
            raise DAGSelfDependencyError("A task cannot depend on itself.")
            
        for d in existing_deps:
            if d.task_id == new_dep.task_id and d.depends_on_task_id == new_dep.depends_on_task_id:
                raise DAGDuplicateError("Dependency already exists.")
                
        # Build adjacency list
        graph: Dict[UUID, List[UUID]] = {}
        for d in existing_deps:
            graph.setdefault(d.depends_on_task_id, []).append(d.task_id)
            
        # Add the new dependency
        graph.setdefault(new_dep.depends_on_task_id, []).append(new_dep.task_id)
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def is_cyclic(node: UUID) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if is_cyclic(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
            
        for node in graph:
            if node not in visited:
                if is_cyclic(node):
                    raise DAGCycleError("Cycle detected in task dependencies.")
