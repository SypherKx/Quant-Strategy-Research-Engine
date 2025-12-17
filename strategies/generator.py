"""
Strategy Generator Module
=========================

🎓 WHAT IS THIS FILE?
This file generates the initial population of strategies and
creates new strategies through evolution (mutation + crossover).

🎓 POPULATION INITIALIZATION:

Instead of starting with just 1 strategy, we start with 8:
- Ensures diversity from the beginning
- Different strategies work in different conditions
- Avoids local optima (getting stuck on one approach)

Initial population includes:
┌────────────────────┬─────────────────────────────────────────┐
│ Strategy Type      │ Purpose                                 │
├────────────────────┼─────────────────────────────────────────┤
│ 1 Conservative     │ Low risk baseline                       │
│ 1 Aggressive       │ High opportunity baseline               │
│ 1 Balanced         │ Middle ground                           │
│ 5 Random           │ Explore parameter space                 │
└────────────────────┴─────────────────────────────────────────┘

🎓 EVOLUTION PROCESS:

Every evolution cycle (e.g., daily):

1. EVALUATE: Rank strategies by performance
2. SELECT: Keep top 75%, retire bottom 25%
3. REPRODUCE: Winners create offspring
4. MUTATE: Some offspring get random changes
5. RESET: If all strategies fail, restart

This mimics natural selection:
- Good strategies survive
- Bad strategies die
- Children inherit traits from parents
- Mutations introduce variation

🎓 GENERATION TRACKING:

We track generations to understand evolution:
- Gen 1: Initial population
- Gen 2: First evolution cycle
- Gen N: Nth cycle

Higher generation = more evolved (hopefully better!)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import random
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger, log_evolution_event
from strategies.strategy_dna import StrategyDNA


@dataclass
class EvolutionStats:
    """
    Statistics about an evolution cycle.
    
    🎓 Useful for analysis and reporting.
    """
    generation: int
    strategies_before: int
    strategies_after: int
    retired_count: int
    created_count: int
    mutated_count: int
    crossover_count: int
    best_strategy_id: str
    worst_strategy_id: str
    avg_performance: float


class StrategyGenerator:
    """
    Generates and evolves strategy populations.
    
    🎓 USAGE:
    generator = StrategyGenerator()
    
    # Create initial population
    strategies = generator.create_initial_population()
    
    # After evaluation, evolve
    new_population = generator.evolve(ranked_strategies)
    """
    
    def __init__(
        self,
        population_size: int = None,
        retire_percent: float = None,
        mutation_rate: float = None
    ):
        """
        Initialize the generator.
        
        Args:
            population_size: Number of strategies to maintain
            retire_percent: Percentage to retire each cycle
            mutation_rate: Probability of mutation per offspring
        """
        self.population_size = population_size or settings.INITIAL_POPULATION_SIZE
        self.retire_percent = retire_percent or settings.RETIRE_BOTTOM_PERCENT
        self.mutation_rate = mutation_rate or settings.MUTATION_RATE
        
        self.current_generation = 1
        self.evolution_history: List[EvolutionStats] = []
    
    def create_initial_population(self) -> List[StrategyDNA]:
        """
        Create the initial strategy population.
        
        🎓 Includes preset strategies for baseline comparison
        plus random strategies for exploration.
        
        Returns:
            List of StrategyDNA objects
        """
        population = []
        
        # Add preset strategies (3 total)
        population.append(StrategyDNA.conservative())
        log_evolution_event(
            "CREATED", population[-1].id, 
            "Initial population - Conservative baseline"
        )
        
        population.append(StrategyDNA.aggressive())
        log_evolution_event(
            "CREATED", population[-1].id,
            "Initial population - Aggressive baseline"
        )
        
        population.append(StrategyDNA.balanced())
        log_evolution_event(
            "CREATED", population[-1].id,
            "Initial population - Balanced baseline"
        )
        
        # Fill rest with random strategies
        remaining = self.population_size - len(population)
        for _ in range(remaining):
            dna = StrategyDNA.random(generation=1)
            population.append(dna)
            log_evolution_event(
                "CREATED", dna.id,
                f"Initial population - Random variant"
            )
        
        logger.info(f"🧬 Created initial population: {len(population)} strategies")
        
        return population
    
    def evolve(
        self,
        ranked_strategies: List[Tuple[StrategyDNA, float]]
    ) -> List[StrategyDNA]:
        """
        Evolve the population based on performance.
        
        🎓 This is called after each evaluation period.
        
        Args:
            ranked_strategies: List of (strategy, performance_score) tuples
                              sorted by performance (best first)
        
        Returns:
            New population for next cycle
        """
        if not ranked_strategies:
            logger.warning("No strategies to evolve, creating new population")
            return self.create_initial_population()
        
        self.current_generation += 1
        
        # Calculate how many to keep
        n_keep = max(2, int(len(ranked_strategies) * (1 - self.retire_percent)))
        n_retire = len(ranked_strategies) - n_keep
        
        # Split into survivors and retired
        survivors = ranked_strategies[:n_keep]
        retired = ranked_strategies[n_keep:]
        
        # Log retirements
        for dna, score in retired:
            log_evolution_event(
                "RETIRED", dna.id,
                f"Poor performance (score: {score:.4f})"
            )
        
        # Start new population with survivors
        new_population = [dna for dna, _ in survivors]
        
        # Generate offspring to fill population
        n_needed = self.population_size - len(new_population)
        offspring_count = 0
        mutant_count = 0
        crossover_count = 0
        
        while len(new_population) < self.population_size:
            # Choose reproduction method
            if random.random() < 0.7 or len(survivors) < 2:
                # Mutation: Mutate a survivor
                parent, _ = random.choice(survivors)
                
                # Determine mutation strength based on performance rank
                parent_rank = survivors.index((parent, _))
                # Top performers get smaller mutations
                mutation_strength = 0.1 + 0.3 * (parent_rank / len(survivors))
                
                child = parent.mutate(mutation_strength=mutation_strength)
                log_evolution_event(
                    "MUTATED", child.id,
                    f"Mutation of {parent.id} (strength: {mutation_strength:.2f})",
                    parent_id=parent.id
                )
                mutant_count += 1
            else:
                # Crossover: Combine two survivors
                parent1, _ = random.choice(survivors)
                parent2, _ = random.choice(survivors)
                
                # Avoid self-crossover
                if parent1.id == parent2.id:
                    parent2, _ = random.choice(survivors)
                
                child = parent1.crossover(parent2)
                log_evolution_event(
                    "CROSSED", child.id,
                    f"Crossover of {parent1.id} x {parent2.id}",
                    parent_id=f"{parent1.id}+{parent2.id}"
                )
                crossover_count += 1
            
            new_population.append(child)
            offspring_count += 1
        
        # Record evolution stats
        best_id = ranked_strategies[0][0].id if ranked_strategies else "N/A"
        worst_id = ranked_strategies[-1][0].id if ranked_strategies else "N/A"
        avg_perf = sum(score for _, score in ranked_strategies) / len(ranked_strategies)
        
        stats = EvolutionStats(
            generation=self.current_generation,
            strategies_before=len(ranked_strategies),
            strategies_after=len(new_population),
            retired_count=n_retire,
            created_count=offspring_count,
            mutated_count=mutant_count,
            crossover_count=crossover_count,
            best_strategy_id=best_id,
            worst_strategy_id=worst_id,
            avg_performance=avg_perf
        )
        self.evolution_history.append(stats)
        
        logger.info(
            f"🧬 Evolution complete: Gen {self.current_generation} | "
            f"Retired: {n_retire} | Created: {offspring_count} | "
            f"Pop: {len(new_population)}"
        )
        
        return new_population
    
    def introduce_diversity(
        self,
        current_population: List[StrategyDNA],
        n_random: int = 2
    ) -> List[StrategyDNA]:
        """
        Introduce random strategies to prevent stagnation.
        
        🎓 Sometimes populations converge to similar strategies.
        Adding random ones helps explore new areas.
        
        Args:
            current_population: Current strategies
            n_random: Number of random strategies to add
        
        Returns:
            Population with random additions
        """
        for _ in range(n_random):
            random_dna = StrategyDNA.random(generation=self.current_generation)
            current_population.append(random_dna)
            log_evolution_event(
                "INJECTED", random_dna.id,
                "Random injection for diversity"
            )
        
        # Remove worst if over population limit
        while len(current_population) > self.population_size:
            current_population.pop()
        
        logger.info(f"🌱 Injected {n_random} random strategies for diversity")
        
        return current_population
    
    def get_evolution_summary(self) -> str:
        """
        Get a summary of evolution history.
        
        🎓 Useful for reports and dashboard.
        """
        if not self.evolution_history:
            return "No evolution cycles completed yet."
        
        lines = [
            "Evolution History",
            "=" * 50,
            f"Total Generations: {self.current_generation}",
            "",
            "Recent Cycles:",
        ]
        
        # Show last 5 cycles
        for stats in self.evolution_history[-5:]:
            lines.append(
                f"  Gen {stats.generation}: "
                f"Retired {stats.retired_count}, "
                f"Created {stats.created_count}, "
                f"Avg Score: {stats.avg_performance:.4f}"
            )
        
        return "\n".join(lines)
    
    def get_lineage(self, strategy_id: str, population: List[StrategyDNA]) -> List[str]:
        """
        Trace the ancestry of a strategy.
        
        🎓 Shows the evolution path that led to this strategy.
        
        Returns:
            List of ancestor IDs from oldest to youngest
        """
        lineage = [strategy_id]
        
        # Build ID to DNA map
        id_map = {dna.id: dna for dna in population}
        
        current_id = strategy_id
        while current_id in id_map:
            parent_id = id_map[current_id].parent_id
            if parent_id and "+" not in parent_id:  # Not a crossover
                if parent_id in id_map:
                    lineage.append(parent_id)
                    current_id = parent_id
                else:
                    break
            else:
                break
        
        return list(reversed(lineage))


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_generator: Optional[StrategyGenerator] = None


def get_strategy_generator() -> StrategyGenerator:
    """Get or create the singleton strategy generator."""
    global _generator
    
    if _generator is None:
        _generator = StrategyGenerator()
    
    return _generator


# =========================================================
# MAIN - Test generator
# =========================================================

if __name__ == "__main__":
    print("🧬 Testing Strategy Generator...")
    print()
    
    generator = StrategyGenerator(population_size=8)
    
    # Create initial population
    population = generator.create_initial_population()
    print(f"✅ Created {len(population)} strategies")
    
    for dna in population:
        print(f"   • {dna.name} (Gen {dna.generation})")
    
    print()
    
    # Simulate performance scores
    import random
    ranked = [
        (dna, random.random())
        for dna in population
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)
    
    print("📊 Simulated Rankings:")
    for dna, score in ranked:
        print(f"   {dna.name}: {score:.4f}")
    
    print()
    
    # Evolve
    new_population = generator.evolve(ranked)
    print(f"✅ Evolution complete. New population: {len(new_population)}")
    
    for dna in new_population:
        parent_info = f" (from {dna.parent_id})" if dna.parent_id else ""
        print(f"   • {dna.name} Gen {dna.generation}{parent_info}")
    
    print()
    print(generator.get_evolution_summary())
