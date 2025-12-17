"""
Strategy DNA Module
===================

🎓 WHAT IS THIS FILE?
This file defines the "DNA" of a trading strategy - the set of
parameters that completely define how a strategy behaves.

🎓 WHY "DNA" METAPHOR?

Just like biological DNA:
1. Defines traits: Each parameter controls a behavior
2. Can mutate: Small changes create new variants
3. Can crossover: Combine two strategies' traits
4. Evolves: Better DNA survives, worse dies

🎓 STRATEGY DNA PARAMETERS EXPLAINED:

┌─────────────────────────┬──────────────────────────────────────────────────┐
│ Parameter               │ What It Controls                                 │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ min_spread_threshold    │ Minimum NSE-BSE spread to trade (%)              │
│                         │ Range: 0.02% - 0.5%                              │
│                         │ Higher = fewer but "safer" trades                │
│                         │ Lower = more trades but smaller profits          │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ stability_ticks         │ Ticks spread must stay favorable before trade    │
│                         │ Range: 1 - 10                                    │
│                         │ Higher = more confirmation, less noise           │
│                         │ Lower = faster entry, more noise                 │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ latency_buffer_pct      │ Buffer added to account for execution delay      │
│                         │ Range: 0.01% - 0.1%                              │
│                         │ Higher = more conservative, fewer fills          │
│                         │ Lower = aggressive, may get slippage             │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ position_size_pct       │ % of capital to use per trade                    │
│                         │ Range: 1% - 10%                                  │
│                         │ Higher = more profit/loss per trade              │
│                         │ Lower = safer, slower growth                     │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ max_hold_seconds        │ Maximum time to hold before forced exit          │
│                         │ Range: 10 - 300 seconds                          │
│                         │ Lower = scalping style                           │
│                         │ Higher = swing style                             │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ preferred_session       │ Which session to trade in                        │
│                         │ 'all', 'opening', 'mid', 'closing'               │
│                         │ Different sessions have different volatility     │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ volatility_preference   │ Which volatility regime to prefer                │
│                         │ 'all', 'low', 'medium', 'high'                   │
│                         │ Match strategy to market conditions              │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ take_profit_pct         │ Exit at this profit %                            │
│                         │ Range: 0.05% - 0.5%                              │
│                         │ Higher = hold for bigger profits                 │
├─────────────────────────┼──────────────────────────────────────────────────┤
│ stop_loss_pct           │ Exit at this loss %                              │
│                         │ Range: 0.1% - 0.5%                               │
│                         │ Lower = cut losses fast                          │
└─────────────────────────┴──────────────────────────────────────────────────┘

🎓 DNA ENCODING:
DNA can be represented as a vector for mathematical operations:
[spread, stability, latency, position, hold_time, session, vol_pref, tp, sl]

This enables:
- Distance calculation between strategies
- Interpolation (crossover)
- Direction-based mutation
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, Dict, List, Any
import uuid
import random
import copy
import json


# Type definitions for clarity
SessionPreference = Literal['all', 'opening', 'mid', 'closing']
VolatilityPreference = Literal['all', 'low', 'medium', 'high']


@dataclass
class StrategyDNA:
    """
    Complete definition of a strategy's behavior.
    
    🎓 All the "genes" that control how the strategy trades.
    """
    
    # Identity
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    generation: int = 1
    parent_id: Optional[str] = None
    
    # Core trading parameters
    min_spread_threshold: float = 0.05      # 0.05% minimum spread
    stability_ticks: int = 3                # 3 ticks of stability
    latency_buffer_pct: float = 0.02        # 0.02% buffer
    position_size_pct: float = 5.0          # 5% of capital per trade
    max_hold_seconds: int = 60              # 1 minute max hold
    
    # Environment preferences
    preferred_session: SessionPreference = 'all'
    volatility_preference: VolatilityPreference = 'all'
    
    # Exit rules
    take_profit_pct: float = 0.1            # 0.1% take profit
    stop_loss_pct: float = 0.2              # 0.2% stop loss
    
    # Metadata
    created_at: str = field(default_factory=lambda: "")
    
    def __post_init__(self):
        from datetime import datetime
        if not self.name:
            self.name = f"Strategy-{self.id.upper()[:4]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    # =========================================================
    # FACTORY METHODS
    # =========================================================
    
    @classmethod
    def random(cls, generation: int = 1, parent_id: Optional[str] = None) -> 'StrategyDNA':
        """
        Generate a completely random strategy DNA.
        
        🎓 Used for initial population generation.
        Parameters are randomly selected from valid ranges.
        """
        return cls(
            generation=generation,
            parent_id=parent_id,
            
            # Random parameters within reasonable ranges
            min_spread_threshold=round(random.uniform(0.02, 0.20), 3),
            stability_ticks=random.randint(1, 8),
            latency_buffer_pct=round(random.uniform(0.01, 0.08), 3),
            position_size_pct=round(random.uniform(2.0, 8.0), 1),
            max_hold_seconds=random.choice([15, 30, 45, 60, 90, 120, 180]),
            
            preferred_session=random.choice(['all', 'opening', 'mid', 'closing']),
            volatility_preference=random.choice(['all', 'low', 'medium', 'high']),
            
            take_profit_pct=round(random.uniform(0.05, 0.30), 3),
            stop_loss_pct=round(random.uniform(0.10, 0.40), 3),
        )
    
    @classmethod
    def conservative(cls) -> 'StrategyDNA':
        """
        Create a conservative strategy DNA.
        
        🎓 Low risk, fewer trades, more confirmation.
        Good for learning and stable returns.
        """
        return cls(
            name="Conservative",
            min_spread_threshold=0.15,
            stability_ticks=6,
            latency_buffer_pct=0.05,
            position_size_pct=3.0,
            max_hold_seconds=90,
            preferred_session='mid',
            volatility_preference='low',
            take_profit_pct=0.15,
            stop_loss_pct=0.20,
        )
    
    @classmethod
    def aggressive(cls) -> 'StrategyDNA':
        """
        Create an aggressive strategy DNA.
        
        🎓 High risk, more trades, quick entries.
        Can make/lose more money faster.
        """
        return cls(
            name="Aggressive",
            min_spread_threshold=0.03,
            stability_ticks=2,
            latency_buffer_pct=0.01,
            position_size_pct=7.0,
            max_hold_seconds=30,
            preferred_session='all',
            volatility_preference='high',
            take_profit_pct=0.08,
            stop_loss_pct=0.25,
        )
    
    @classmethod
    def balanced(cls) -> 'StrategyDNA':
        """
        Create a balanced strategy DNA.
        
        🎓 Middle ground between conservative and aggressive.
        """
        return cls(
            name="Balanced",
            min_spread_threshold=0.08,
            stability_ticks=4,
            latency_buffer_pct=0.03,
            position_size_pct=5.0,
            max_hold_seconds=60,
            preferred_session='mid',
            volatility_preference='medium',
            take_profit_pct=0.12,
            stop_loss_pct=0.18,
        )
    
    # =========================================================
    # MUTATION
    # =========================================================
    
    def mutate(self, mutation_strength: float = 0.2) -> 'StrategyDNA':
        """
        Create a mutated copy of this DNA.
        
        🎓 Mutation = Small random changes to existing strategy.
        
        Args:
            mutation_strength: How much to change (0.0 to 1.0)
                0.1 = small changes
                0.5 = moderate changes
                1.0 = large changes
        
        Returns:
            New StrategyDNA with mutations applied
        """
        # Create copy
        mutated = copy.deepcopy(self)
        mutated.id = uuid.uuid4().hex[:8]
        mutated.name = f"Mutant-{mutated.id.upper()[:4]}"
        mutated.parent_id = self.id
        mutated.generation = self.generation + 1
        from datetime import datetime
        mutated.created_at = datetime.now().isoformat()
        
        # Mutate numeric parameters
        def mutate_value(value: float, min_val: float, max_val: float) -> float:
            """Apply random mutation to a numeric value."""
            # Gaussian noise proportional to range
            range_size = max_val - min_val
            noise = random.gauss(0, mutation_strength * range_size * 0.3)
            new_value = value + noise
            return round(max(min_val, min(max_val, new_value)), 3)
        
        # Apply mutations with probability
        if random.random() < 0.5:
            mutated.min_spread_threshold = mutate_value(
                self.min_spread_threshold, 0.02, 0.20
            )
        
        if random.random() < 0.5:
            mutated.stability_ticks = max(1, min(10, 
                self.stability_ticks + random.randint(-2, 2)
            ))
        
        if random.random() < 0.4:
            mutated.latency_buffer_pct = mutate_value(
                self.latency_buffer_pct, 0.01, 0.08
            )
        
        if random.random() < 0.4:
            mutated.position_size_pct = round(mutate_value(
                self.position_size_pct, 2.0, 8.0
            ), 1)
        
        if random.random() < 0.4:
            mutated.max_hold_seconds = max(15, min(180,
                self.max_hold_seconds + random.randint(-30, 30)
            ))
        
        if random.random() < 0.3:
            mutated.take_profit_pct = mutate_value(
                self.take_profit_pct, 0.05, 0.30
            )
        
        if random.random() < 0.3:
            mutated.stop_loss_pct = mutate_value(
                self.stop_loss_pct, 0.10, 0.40
            )
        
        # Mutate categorical parameters (less frequently)
        if random.random() < 0.2:
            mutated.preferred_session = random.choice([
                'all', 'opening', 'mid', 'closing'
            ])
        
        if random.random() < 0.2:
            mutated.volatility_preference = random.choice([
                'all', 'low', 'medium', 'high'
            ])
        
        return mutated
    
    # =========================================================
    # CROSSOVER
    # =========================================================
    
    def crossover(self, other: 'StrategyDNA') -> 'StrategyDNA':
        """
        Create offspring by combining this DNA with another.
        
        🎓 Crossover = Taking traits from two successful strategies.
        Similar to biological reproduction.
        
        Args:
            other: Another strategy to combine with
        
        Returns:
            New StrategyDNA with mixed traits
        """
        child = StrategyDNA()
        child.parent_id = f"{self.id}+{other.id}"
        child.generation = max(self.generation, other.generation) + 1
        child.name = f"Child-{child.id.upper()[:4]}"
        
        # 50/50 inheritance for each trait
        child.min_spread_threshold = random.choice([
            self.min_spread_threshold, other.min_spread_threshold
        ])
        child.stability_ticks = random.choice([
            self.stability_ticks, other.stability_ticks
        ])
        child.latency_buffer_pct = random.choice([
            self.latency_buffer_pct, other.latency_buffer_pct
        ])
        child.position_size_pct = random.choice([
            self.position_size_pct, other.position_size_pct
        ])
        child.max_hold_seconds = random.choice([
            self.max_hold_seconds, other.max_hold_seconds
        ])
        child.preferred_session = random.choice([
            self.preferred_session, other.preferred_session
        ])
        child.volatility_preference = random.choice([
            self.volatility_preference, other.volatility_preference
        ])
        child.take_profit_pct = random.choice([
            self.take_profit_pct, other.take_profit_pct
        ])
        child.stop_loss_pct = random.choice([
            self.stop_loss_pct, other.stop_loss_pct
        ])
        
        return child
    
    # =========================================================
    # COMPATIBILITY CHECK
    # =========================================================
    
    def is_compatible_with_regime(
        self, 
        session: str, 
        volatility: str
    ) -> bool:
        """
        Check if this strategy is suitable for given market regime.
        
        🎓 Strategies can specify preferences for when they trade.
        If regime doesn't match, strategy should sit out.
        """
        # Session check
        if self.preferred_session != 'all':
            if self.preferred_session != session:
                return False
        
        # Volatility check
        if self.volatility_preference != 'all':
            if self.volatility_preference != volatility:
                return False
        
        return True
    
    # =========================================================
    # SERIALIZATION
    # =========================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyDNA':
        """Create from dictionary."""
        return cls(**data)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'StrategyDNA':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    # =========================================================
    # DISPLAY
    # =========================================================
    
    def summary(self) -> str:
        """
        Get a human-readable summary.
        
        🎓 Useful for dashboard and logs.
        """
        return f"""
Strategy: {self.name} (Gen {self.generation})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry Rules:
  • Min spread:     {self.min_spread_threshold:.3f}%
  • Stability:      {self.stability_ticks} ticks
  • Latency buffer: {self.latency_buffer_pct:.3f}%

Position:
  • Size:           {self.position_size_pct:.1f}% of capital
  • Max hold:       {self.max_hold_seconds}s

Exit Rules:
  • Take profit:    {self.take_profit_pct:.3f}%
  • Stop loss:      {self.stop_loss_pct:.3f}%

Preferences:
  • Session:        {self.preferred_session}
  • Volatility:     {self.volatility_preference}
"""


# =========================================================
# MAIN - Test DNA
# =========================================================

if __name__ == "__main__":
    print("🧬 Testing Strategy DNA...")
    print()
    
    # Create random strategy
    random_dna = StrategyDNA.random()
    print("Random Strategy:")
    print(random_dna.summary())
    
    # Create preset strategies
    print("\n" + "="*50)
    conservative = StrategyDNA.conservative()
    print("Conservative Strategy:")
    print(conservative.summary())
    
    # Test mutation
    print("\n" + "="*50)
    mutant = conservative.mutate(mutation_strength=0.3)
    print(f"Mutated from {conservative.name}:")
    print(mutant.summary())
    
    # Test crossover
    print("\n" + "="*50)
    aggressive = StrategyDNA.aggressive()
    child = conservative.crossover(aggressive)
    print("Child of Conservative + Aggressive:")
    print(child.summary())
    
    # Test serialization
    print("\n" + "="*50)
    json_str = random_dna.to_json()
    print(f"JSON (first 200 chars): {json_str[:200]}...")
    
    restored = StrategyDNA.from_json(json_str)
    print(f"Restored: {restored.name} (Generation {restored.generation})")
