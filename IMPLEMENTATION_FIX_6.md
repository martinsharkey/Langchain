# PHASE 2, FIX #6: EXTRACT KNOWLEDGE RULES FROM Q&A
## Convert curiosity agent knowledge into executable trading logic

**Status:** Ready to implement  
**Effort:** 4-6 hours  
**Priority:** HIGH (activates knowledge system)  
**Dependencies:** Fix #3 (real outcomes) recommended

---

## PROBLEM STATEMENT

The curiosity agent acquires valuable knowledge but it's never used:

**Example:**
- Curiosity agent asks: "When does gold spike?"
- LLM answers: "Gold typically spikes 50-200 pips during geopolitical events, wars, elections, central bank interventions"
- Knowledge stored: ✅
- Knowledge used: ❌

**Current behavior:**
```python
# Knowledge exists in database
knowledge_entry = {
    "question": "When does gold spike?",
    "answer": "Gold spikes during geopolitical events...",
    "source": "LLM",
    "created_at": "2026-07-30",
}

# But bot has no way to use it
# Can't trigger: "If geopolitical event, adjust position size"
```

---

## ROOT CAUSE

No mechanism to:
1. Parse Q&A for actionable if-then rules
2. Extract executable conditions
3. Apply rules during trading decisions

---

## IMPLEMENTATION STEPS

### Step 1: Create TradingRule class

**File:** `src/learning/knowledge_base.py` (or create `src/learning/trading_rules.py`)  
**Location:** Add new class

**Add this class:**
```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable

class RuleType(Enum):
    """Types of trading rules that can be extracted."""
    POSITION_SIZING = "position_sizing"
    ENTRY_TIMING = "entry_timing"
    EXIT_TIMING = "exit_timing"
    RISK_MANAGEMENT = "risk_management"
    AVOID_TRADING = "avoid_trading"
    MARKET_CONDITION = "market_condition"

@dataclass
class TradingRule:
    """A trading rule extracted from knowledge."""
    
    rule_id: str
    rule_type: RuleType
    condition: str  # e.g., "geopolitical_event_upcoming"
    action: str  # e.g., "reduce_position_size"
    parameters: dict  # e.g., {"size_multiplier": 0.5}
    source_qa: str  # Which Q&A this came from
    confidence: float  # 0.0 to 1.0, how sure we are
    created_at: datetime
    last_used: datetime = None
    use_count: int = 0
    
    def apply(self, current_state: dict) -> dict:
        """
        Apply this rule to trading state if condition met.
        
        Returns modified state or empty dict if condition not met.
        """
        # Override in subclasses or implement condition evaluation
        pass
```

### Step 2: Create knowledge extraction pipeline

**File:** `src/learning/knowledge_base.py`  
**Location:** Add new method to KnowledgeBase class

**Add this method:**
```python
def extract_trading_rules(self) -> list[TradingRule]:
    """
    Extract trading rules from all Q&A entries.
    
    Uses LLM to parse knowledge entries and extract rules.
    """
    rules = []
    qa_entries = self.get_all_qa_entries()
    
    for entry in qa_entries:
        question = entry["question"]
        answer = entry["answer"]
        
        # Use LLM to extract rules
        extraction_prompt = f"""
        Given this Q&A about trading:
        
        Q: {question}
        A: {answer}
        
        Extract any actionable trading rules as JSON array. For each rule:
        {{
            "rule_type": "position_sizing|entry_timing|exit_timing|risk_management|avoid_trading|market_condition",
            "condition": "When this condition is true...",
            "action": "Then do this action...",
            "parameters": {{"key": "value"}},
            "confidence": 0.0-1.0
        }}
        
        Return only JSON array, no other text.
        """
        
        try:
            llm = get_llm(temperature=0.1)  # Low temp for extraction
            response = llm.invoke(extraction_prompt)
            extracted = json.loads(response)
            
            for rule_dict in extracted:
                rule = TradingRule(
                    rule_id=hashlib.md5(
                        f"{question}{rule_dict['action']}".encode()
                    ).hexdigest(),
                    rule_type=RuleType(rule_dict["rule_type"]),
                    condition=rule_dict["condition"],
                    action=rule_dict["action"],
                    parameters=rule_dict.get("parameters", {}),
                    source_qa=f"{question[:50]}...",
                    confidence=rule_dict.get("confidence", 0.7),
                    created_at=datetime.now(),
                )
                rules.append(rule)
                
                # Store in database
                self._store_rule(rule)
        
        except Exception as e:
            logger.error(f"Error extracting rules from Q&A: {e}")
    
    return rules

def _store_rule(self, rule: TradingRule):
    """Store rule in database."""
    # Create trading_rules table if needed
    cursor = self.conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO trading_rules
        (rule_id, rule_type, condition, action, parameters, source_qa, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rule.rule_id,
        rule.rule_type.value,
        rule.condition,
        rule.action,
        json.dumps(rule.parameters),
        rule.source_qa,
        rule.confidence,
        rule.created_at.isoformat(),
    ))
    self.conn.commit()
```

### Step 3: Evaluate rule conditions during trading

**File:** `src/learning/rule_engine.py` (new file)  
**Location:** Create new file

**Add this class:**
```python
class RuleEngine:
    """Evaluates and applies trading rules."""
    
    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base
        self.rules = []
        self._load_rules()
    
    def _load_rules(self):
        """Load active rules from knowledge base."""
        self.rules = self.kb.get_active_rules()
    
    def evaluate_rules(self, current_state: dict) -> dict:
        """
        Evaluate all rules and return their recommendations.
        
        Args:
            current_state: Dict with market state, indicators, etc.
        
        Returns:
            Dict with rule applications and modifications
        """
        modifications = {
            "position_size_multiplier": 1.0,
            "should_trade": True,
            "warnings": [],
            "applied_rules": [],
        }
        
        for rule in self.rules:
            # Check if condition matches current state
            if self._condition_matches(rule.condition, current_state):
                # Apply the rule
                self._apply_rule(rule, modifications)
                modifications["applied_rules"].append(rule.rule_id)
        
        return modifications
    
    def _condition_matches(self, condition: str, state: dict) -> bool:
        """Check if rule condition matches current state."""
        # Simple condition matching
        # In production, would use more sophisticated parsing
        
        condition_lower = condition.lower()
        
        # Check for event-based conditions
        if "geopolitical_event" in condition_lower:
            return state.get("geopolitical_event_upcoming", False)
        
        if "economic_release" in condition_lower:
            return state.get("major_economic_release_soon", False)
        
        if "volatile" in condition_lower:
            atr = state.get("indicators", {}).get("atr", 0)
            return atr > 20  # High volatility threshold
        
        # Add more conditions as needed
        return False
    
    def _apply_rule(self, rule: TradingRule, modifications: dict):
        """Apply a rule to trading modifications."""
        
        if rule.rule_type == RuleType.POSITION_SIZING:
            multiplier = rule.parameters.get("size_multiplier", 1.0)
            modifications["position_size_multiplier"] *= multiplier
        
        elif rule.rule_type == RuleType.AVOID_TRADING:
            modifications["should_trade"] = False
            modifications["warnings"].append(
                f"Rule: {rule.action} ({rule.confidence:.0%} confidence)"
            )
        
        elif rule.rule_type == RuleType.RISK_MANAGEMENT:
            if "stop_loss" in rule.parameters:
                modifications["stop_loss_adjustment"] = rule.parameters["stop_loss"]
            if "take_profit" in rule.parameters:
                modifications["take_profit_adjustment"] = rule.parameters["take_profit"]
        
        logger.info(
            f"Applied rule {rule.rule_id}: {rule.action} "
            f"(confidence={rule.confidence:.0%})"
        )
```

### Step 4: Integrate rules into trading decision

**File:** `src/main.py`  
**Location:** In `run_risk_check()` or `execute_trade()`

**Add this:**
```python
def run_risk_check(self, signal: dict, strategy_result: dict) -> dict:
    """Run risk check on signal."""
    
    # ← ADD THIS SECTION:
    # Evaluate knowledge-based rules
    if self.knowledge_base:
        current_state = {
            "indicators": strategy_result.get("indicators", {}),
            "geopolitical_event_upcoming": self._check_geopolitical_events(),
            "major_economic_release_soon": self._check_economic_calendar(),
        }
        
        rule_engine = RuleEngine(self.knowledge_base)
        rule_mods = rule_engine.evaluate_rules(current_state)
        
        # Apply position sizing adjustment
        if rule_mods["position_size_multiplier"] != 1.0:
            size_adj = rule_mods["position_size_multiplier"]
            position_size *= size_adj
            console.print(
                f"  [yellow]Rule-based adjustment: "
                f"position size × {size_adj:.2f}[/yellow]"
            )
        
        # Check if rules say to avoid trading
        if not rule_mods["should_trade"]:
            console.print(f"  [yellow]Avoiding trade due to rules:[/yellow]")
            for warning in rule_mods["warnings"]:
                console.print(f"    • {warning}")
            return {"approved": False, "reason": "Rule-based avoidance"}
        
        # Apply other rule modifications
        if "stop_loss_adjustment" in rule_mods:
            signal["stop_loss"] = rule_mods["stop_loss_adjustment"]
        if "take_profit_adjustment" in rule_mods:
            signal["take_profit"] = rule_mods["take_profit_adjustment"]
    
    # Continue with normal risk check...
```

### Step 5: Add helper methods for event detection

**File:** `src/main.py`  
**Location:** Add to TradingBot class

**Add these methods:**
```python
def _check_geopolitical_events(self) -> bool:
    """Check if geopolitical events are upcoming."""
    # In production, would connect to news API or economic calendar
    # For now, return False
    return False

def _check_economic_calendar(self) -> bool:
    """Check if major economic releases are upcoming."""
    # In production, would connect to economic calendar API
    # For now, return False
    return False
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] TradingRule class created and works
- [ ] extract_trading_rules() runs without errors
- [ ] Rules extracted from Q&A entries
- [ ] RuleEngine evaluates conditions
- [ ] Rules applied during trading decision
- [ ] Position sizing adjusted by rules
- [ ] Console shows rule applications
- [ ] Code compiles without errors

**Test scenario:**
1. Manually create Q&A entry: "Avoid trading on Friday evenings"
2. Extract rules → should get "avoid_trading" rule
3. Run bot on Friday evening → should skip trade
4. Check console: "Rule-based avoidance" message

---

## DEPENDENCIES

**Depends on:** Fix #3 (real outcomes) recommended, but works standalone

**Enables:** Full autonomous trading system

---

## ESTIMATED TIME BREAKDOWN

- TradingRule class: 30 min
- Knowledge extraction: 60 min
- Rule engine: 60 min
- Integration: 45 min
- Testing + debugging: 60-90 min

**Total: 4-6 hours**

---

## NEXT STEP

After Fix #6, implement Fix #7 (persistent weight learning)
