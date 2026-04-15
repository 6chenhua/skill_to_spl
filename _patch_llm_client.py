"""Script to patch llm_client.py with model parameter support."""
import re

# Read the original file
with open('pipeline/llm_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add StepLLMConfig after SessionUsage class
stepllmconfig_code = '''

@dataclass
class StepLLMConfig:
    """
    Maps step names to their LLM model configuration.

    Allows different steps to use different models. If a step name is not
    found in step_configs, the default config is used.

    Attributes:
        default: The default LLMConfig to use for steps not in step_configs.
        step_configs: A dict mapping step names to their specific LLMConfig.
    """
    default: LLMConfig = field(default_factory=LLMConfig)
    step_configs: dict[str, LLMConfig] = field(default_factory=dict)

    def get(self, step_name: str) -> LLMConfig:
        """Get the LLMConfig for a given step name, falling back to default."""
        return self.step_configs.get(step_name, self.default)

    def get_model(self, step_name: str) -> str | None:
        """Get just the model name for a given step, or None for default."""
        if step_name in self.step_configs:
            cfg = self.step_configs[step_name]
            return cfg.model if cfg.model else None
        return None

'''

# Insert after SessionUsage class
pattern = r'(class LLMError\(Exception\):)'
content = re.sub(pattern, stepllmconfig_code + '\\1', content)

# 2. Update call() method signature
content = content.replace(
    '''def call(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> str:
        """
        Send a single-turn system + user prompt. Returns the full response text.
        Retries on transient errors with exponential backoff.
        """
        delay = self.config.retry_base_delay''',
    '''def call(
        self,
        step_name: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> str:
        """
        Send a single-turn system + user prompt. Returns the full response text.
        Retries on transient errors with exponential backoff.

        Args:
            step_name: Name of the step for logging and usage tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If not provided, uses self.config.model.
        """
        effective_model = model or self.config.model
        delay = self.config.retry_base_delay'''
)

# 3. Update model in call() method
content = content.replace(
    'model=self.config.model,\n            max_tokens=self.config.max_tokens,\n            temperature=self.config.temperature,\n            messages=[\n                {"role": "system", "content": system},\n                {"role": "user", "content": user}\n            ],',
    'model=effective_model,\n            max_tokens=self.config.max_tokens,\n            temperature=self.config.temperature,\n            messages=[\n                {"role": "system", "content": system},\n                {"role": "user", "content": user}\n            ],'
)

# 4. Update call_json() method signature
content = content.replace(
    '''def call_json(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> Any:''',
    '''def call_json(
        self,
        step_name: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> Any:'''
)

# 5. Update call_json() to pass model to call()
content = content.replace(
    'raw = self.call(step_name=step_name, system=system, user=user)',
    'raw = self.call(step_name=step_name, system=system, user=user, model=model)'
)

# 6. Update async_call() method signature  
content = content.replace(
    '''async def async_call(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> str:
        """
        Async version of call(). Send a single-turn system + user prompt.
        Returns the full response text. Retries on transient errors.
        """
        delay = self.config.retry_base_delay''',
    '''async def async_call(
        self,
        step_name: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> str:
        """
        Async version of call(). Send a single-turn system + user prompt.
        Returns the full response text. Retries on transient errors.

        Args:
            step_name: Name of the step for logging and usage tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If not provided, uses self.config.model.
        """
        effective_model = model or self.config.model
        delay = self.config.retry_base_delay'''
)

# 7. Update async_call_json() signature
content = content.replace(
    '''async def async_call_json(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> Any:''',
    '''async def async_call_json(
        self,
        step_name: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> Any:'''
)

# 8. Update async_call_json() to pass model
content = content.replace(
    'raw = await self.async_call(step_name=step_name, system=system, user=user)',
    'raw = await self.async_call(step_name=step_name, system=system, user=user, model=model)'
)

# Write the modified file
with open('pipeline/llm_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully patched llm_client.py")
