"""
Prompt management with support for both text and YAML formats
"""

import re
import yaml
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .config import Config
from .exceptions import PromptError


logger = logging.getLogger(__name__)


@dataclass
class SyncStep:
    """Individual build step"""
    number: int
    content: str
    description: Optional[str] = None
    estimated_time: Optional[int] = None  # minutes
    dependencies: Optional[List[int]] = None
    tags: Optional[List[str]] = None


@dataclass 
class SyncPrompt:
    """Build prompt data model"""
    name: str
    filename: str
    format: str  # 'text' or 'yaml'
    initial_prompt: str
    steps: List[SyncStep]
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def estimated_time(self, config: Config) -> str:
        """Estimate total build time"""
        # Use a reasonable estimate of 5 minutes per step
        total_minutes = len(self.steps) * 5
        
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"


class PromptManager:
    """Manages build prompts in multiple formats"""
    
    def __init__(self, config: Config):
        self.config = config
        self.prompts_dir = config.prompts_dir
    
    def list_prompts(self) -> List[SyncPrompt]:
        """List all available prompts"""
        prompts = []
        
        # Find text prompts
        for txt_file in self.prompts_dir.glob("*.txt"):
            try:
                prompt = self._load_text_prompt(txt_file)
                prompts.append(prompt)
            except Exception as e:
                logger.warning(f"Failed to load {txt_file}: {e}")
        
        # Find YAML prompts
        for yaml_file in self.prompts_dir.glob("*.yaml"):
            try:
                prompt = self._load_yaml_prompt(yaml_file)
                prompts.append(prompt)
            except Exception as e:
                logger.warning(f"Failed to load {yaml_file}: {e}")
        
        for yml_file in self.prompts_dir.glob("*.yml"):
            try:
                prompt = self._load_yaml_prompt(yml_file)
                prompts.append(prompt)
            except Exception as e:
                logger.warning(f"Failed to load {yml_file}: {e}")
        
        return sorted(prompts, key=lambda p: p.name)
    
    def load_prompt(self, filename: str) -> SyncPrompt:
        """Load a specific prompt file"""
        # Handle both absolute and relative paths
        if Path(filename).is_absolute():
            prompt_path = Path(filename)
        else:
            prompt_path = self.prompts_dir / filename
        
        if not prompt_path.exists():
            # Try without directory
            prompt_path = Path(filename)
            if not prompt_path.exists():
                raise PromptError(f"Prompt file not found: {filename}")
        
        # Determine format by extension
        ext = prompt_path.suffix.lower()
        if ext == '.txt':
            return self._load_text_prompt(prompt_path)
        elif ext in ['.yaml', '.yml']:
            return self._load_yaml_prompt(prompt_path)
        else:
            raise PromptError(f"Unsupported prompt format: {ext}")
    
    def _load_text_prompt(self, path: Path) -> SyncPrompt:
        """Load a text format prompt (original format)"""
        content = path.read_text(encoding='utf-8')
        
        # Extract Raivyn [build] section
        build_match = re.search(r'# Raivyn \[build\](.*?)(?=\n#|$)', content, re.DOTALL)
        if not build_match:
            raise PromptError(f"No '# Raivyn [build]' section found in {path}")
        
        initial_prompt = build_match.group(1).strip()
        
        # Extract numbered steps
        steps = []
        step_pattern = r'^(\d+)\.\s+(.+?)(?=^\d+\.|$)'
        matches = re.findall(step_pattern, content, re.MULTILINE | re.DOTALL)
        
        for step_num, step_content in matches:
            # Clean up step content
            step_content = step_content.strip()
            
            # Extract first line as description
            lines = step_content.split('\n')
            description = lines[0] if lines else ""
            if len(description) > 100:
                description = description[:97] + "..."
            
            steps.append(SyncStep(
                number=int(step_num),
                content=step_content,
                description=description
            ))
        
        if not steps:
            raise PromptError(f"No numbered steps found in {path}")
        
        # Extract project name from prompt
        name = self._extract_project_name(initial_prompt, path.stem)
        
        return SyncPrompt(
            name=name,
            filename=path.name,
            format='text',
            initial_prompt=initial_prompt,
            steps=steps,
            description=None,
            metadata={}
        )
    
    def _load_yaml_prompt(self, path: Path) -> SyncPrompt:
        """Load a YAML format prompt"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict):
            raise PromptError(f"Invalid YAML structure in {path}")
        
        # Validate required fields
        if 'name' not in data:
            raise PromptError(f"Missing 'name' field in {path}")
        if 'initial_prompt' not in data:
            raise PromptError(f"Missing 'initial_prompt' field in {path}")
        if 'steps' not in data or not isinstance(data['steps'], list):
            raise PromptError(f"Missing or invalid 'steps' field in {path}")
        
        # Parse steps
        steps = []
        for i, step_data in enumerate(data['steps'], 1):
            if isinstance(step_data, str):
                # Simple string step
                steps.append(SyncStep(
                    number=i,
                    content=step_data,
                    description=step_data.split('\n')[0][:100]
                ))
            elif isinstance(step_data, dict):
                # Detailed step
                if 'content' not in step_data:
                    raise PromptError(f"Step {i} missing 'content' field in {path}")
                
                steps.append(SyncStep(
                    number=step_data.get('number', i),
                    content=step_data['content'],
                    description=step_data.get('description', step_data['content'].split('\n')[0][:100]),
                    estimated_time=step_data.get('estimated_time'),
                    dependencies=step_data.get('dependencies'),
                    tags=step_data.get('tags')
                ))
            else:
                raise PromptError(f"Invalid step {i} format in {path}")
        
        return SyncPrompt(
            name=data['name'],
            filename=path.name,
            format='yaml',
            initial_prompt=data['initial_prompt'],
            steps=steps,
            description=data.get('description'),
            metadata=data.get('metadata', {})
        )
    
    def _extract_project_name(self, initial_prompt: str, filename: str) -> str:
        """Extract project name from prompt content or filename"""
        # Try to find project name in prompt
        patterns = [
            r'build\s+(\w+)',
            r'create\s+(\w+)',
            r'develop\s+(\w+)',
            r'implement\s+(\w+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, initial_prompt, re.IGNORECASE)
            if match:
                return match.group(1).title()
        
        # Fall back to filename
        name = filename.replace('build_prompt_', '').replace('build_prompts_', '')
        name = name.replace('_', ' ').replace('-', ' ')
        return name.title()
    
    def select_prompt(self) -> SyncPrompt:
        """Interactive prompt selection"""
        prompts = self.list_prompts()
        
        if not prompts:
            raise PromptError("No prompt files found")
        
        if len(prompts) == 1:
            logger.info(f"Using single available prompt: {prompts[0].name}")
            return prompts[0]
        
        # Display options
        print("\nAvailable prompts:")
        for i, prompt in enumerate(prompts, 1):
            desc = f" - {prompt.description}" if prompt.description else ""
            print(f"{i}. {prompt.name} ({len(prompt.steps)} steps){desc}")
        
        # Get selection
        while True:
            try:
                choice = input("\nSelect prompt (number): ")
                idx = int(choice) - 1
                if 0 <= idx < len(prompts):
                    return prompts[idx]
                else:
                    print("Invalid selection. Please try again.")
            except (ValueError, KeyboardInterrupt):
                raise PromptError("Prompt selection cancelled")
    
    def validate_prompt(self, prompt: SyncPrompt) -> List[str]:
        """Validate a prompt and return any warnings"""
        warnings = []
        
        # Check initial prompt
        if len(prompt.initial_prompt) < 50:
            warnings.append("Initial prompt seems very short")
        
        # Check steps
        if len(prompt.steps) == 0:
            warnings.append("No sync steps found")
        
        # Check step numbering
        expected = 1
        for step in prompt.steps:
            if step.number != expected:
                warnings.append(f"Step numbering gap: expected {expected}, got {step.number}")
            expected = step.number + 1
        
        # Check for very long steps
        for step in prompt.steps:
            if len(step.content) > 5000:
                warnings.append(f"Step {step.number} is very long ({len(step.content)} chars)")
        
        return warnings
    
    def convert_prompt(self, input_file: str, output_file: str):
        """Convert prompt between formats"""
        input_path = Path(input_file)
        output_path = Path(output_file)
        
        # Load prompt
        prompt = self.load_prompt(input_file)
        
        # Determine output format
        output_ext = output_path.suffix.lower()
        
        if output_ext == '.txt':
            self._save_text_prompt(prompt, output_path)
        elif output_ext in ['.yaml', '.yml']:
            self._save_yaml_prompt(prompt, output_path)
        else:
            raise PromptError(f"Unsupported output format: {output_ext}")
    
    def _save_text_prompt(self, prompt: SyncPrompt, path: Path):
        """Save prompt in text format"""
        content = f"# Raivyn [build]\n{prompt.initial_prompt}\n\n# Sync Steps\n"
        
        for step in prompt.steps:
            content += f"{step.number}. {step.content}\n"
        
        path.write_text(content, encoding='utf-8')
    
    def _save_yaml_prompt(self, prompt: SyncPrompt, path: Path):
        """Save prompt in YAML format"""
        data = {
            'name': prompt.name,
            'description': prompt.description,
            'initial_prompt': prompt.initial_prompt,
            'steps': []
        }
        
        for step in prompt.steps:
            if step.estimated_time or step.dependencies or step.tags:
                # Save as detailed step
                step_data = {
                    'number': step.number,
                    'content': step.content,
                    'description': step.description
                }
                if step.estimated_time:
                    step_data['estimated_time'] = step.estimated_time
                if step.dependencies:
                    step_data['dependencies'] = step.dependencies
                if step.tags:
                    step_data['tags'] = step.tags
                data['steps'].append(step_data)
            else:
                # Save as simple string
                data['steps'].append(step.content)
        
        if prompt.metadata:
            data['metadata'] = prompt.metadata
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, width=120)
    
    def create_template(self, name: str, template_type: str = 'generic') -> Path:
        """Create a new prompt template"""
        templates = {
            'generic': {
                'name': name,
                'description': f'Build prompt for {name}',
                'initial_prompt': f'You are an expert developer. You will build {name}.\n\nRespond with "Ready to build {name}" when you are prepared to start.',
                'steps': [
                    'Initialize the project with proper structure and dependencies',
                    'Implement core functionality',
                    'Add error handling and validation',
                    'Create comprehensive tests',
                    'Add documentation',
                    'Prepare for deployment'
                ]
            },
            'webapp': {
                'name': name,
                'description': f'Web application build prompt for {name}',
                'initial_prompt': f'You are an expert full-stack developer. You will build {name} - a modern web application.\n\nRespond with "Ready to build {name}" when prepared.',
                'steps': [
                    'Set up the project with React/Vue/Angular and TypeScript',
                    'Design and implement the database schema',
                    'Create the backend API with proper authentication',
                    'Build the frontend UI components',
                    'Implement state management and data flow',
                    'Add responsive design and accessibility',
                    'Create unit and integration tests',
                    'Set up CI/CD pipeline',
                    'Deploy to production environment'
                ]
            },
            'mobile': {
                'name': name,
                'description': f'Mobile app build prompt for {name}',
                'initial_prompt': f'You are an expert mobile developer. You will build {name} - a cross-platform mobile application.\n\nRespond with "Ready to build {name}" when prepared.',
                'steps': [
                    'Initialize React Native/Flutter project with TypeScript',
                    'Set up navigation and app structure',
                    'Design and implement UI screens',
                    'Integrate with backend services',
                    'Implement offline functionality',
                    'Add push notifications',
                    'Optimize performance and animations',
                    'Test on iOS and Android',
                    'Prepare app store submissions'
                ]
            }
        }
        
        template = templates.get(template_type, templates['generic'])
        template['name'] = name
        
        # Save as YAML
        filename = f"{name.lower().replace(' ', '_')}.yaml"
        output_path = self.prompts_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(template, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Created template at {output_path}")
        return output_path