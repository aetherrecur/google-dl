# Python Clean Code and Best Practices Guide

A comprehensive reference for writing maintainable, readable, and robust Python code.

---

## Table of Contents

1. [Universal Software Principles](#universal-software-principles)
2. [Python Naming Conventions](#python-naming-conventions)
3. [Import Organization](#import-organization)
4. [The Law of Demeter](#the-law-of-demeter)
5. [Conditional Clarity](#conditional-clarity)
6. [Guard Clauses and Early Returns](#guard-clauses-and-early-returns)
7. [Code Organization Patterns](#code-organization-patterns)
8. [Avoiding Common Pitfalls](#avoiding-common-pitfalls)
9. [Quick Reference Checklists](#quick-reference-checklists)

---

## Universal Software Principles

### SOLID Principles

| Principle | Description | Key Question |
|-----------|-------------|--------------|
| **Single Responsibility** | A class/function should have one reason to change | Does this do exactly one thing? |
| **Open/Closed** | Open for extension, closed for modification | Can I extend without modifying? |
| **Liskov Substitution** | Subclasses must be substitutable for base classes | Does the subclass honor the contract? |
| **Interface Segregation** | Prefer small, focused interfaces | Are clients forced to depend on unused methods? |
| **Dependency Inversion** | Depend on abstractions, not concretions | Am I depending on an interface or implementation? |

### Core Principles

| Principle | Definition | Application |
|-----------|------------|-------------|
| **DRY** | Don't Repeat Yourself | Every piece of logic has a single, unambiguous representation |
| **KISS** | Keep It Simple | Avoid over-engineering; prefer straightforward solutions |
| **YAGNI** | You Aren't Gonna Need It | Implement only what is currently required |
| **Fail Fast** | Detect and report errors immediately | Validate inputs early; throw exceptions at point of failure |
| **Separation of Concerns** | Divide system into distinct sections | Each module handles one specific responsibility |
| **Composition over Inheritance** | Prefer "has-a" over "is-a" relationships | Build behavior by combining objects, not class hierarchies |
| **Single Source of Truth** | One authoritative location for each piece of data | Avoid duplicate definitions; use references |

---

## Python Naming Conventions

### PEP 8 Standards

```python
# Variables and functions: snake_case
user_count = 0
def calculate_total():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_CONNECTIONS = 100
DEFAULT_TIMEOUT = 30

# Classes: PascalCase
class UserAccount:
    pass

# Private members: _leading_underscore
class Example:
    def __init__(self):
        self._internal_state = None

# Module-level "dunder" names
__version__ = "1.0.0"
__author__ = "Developer"
```

### Positive Naming

```python
# AVOID - Negative naming
def is_not_valid(user):
    return not user.is_active

# PREFER - Positive naming
def is_valid(user):
    return user.is_active
```

### Boolean Naming

```python
# Use 'is_', 'has_', 'can_', 'should_' prefixes
is_active = True
has_permission = False
can_edit = True
should_retry = False
```

---

## Import Organization

### Import Order

Imports belong at the top of the file, after module docstrings, organized into groups separated by blank lines:

```python
"""Module docstring describing purpose."""

# --- Standard Library ---
import os
import sys
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

# --- Third-Party Libraries ---
import numpy as np
import pandas as pd
from flask import Flask

# --- Local Application Imports ---
from myproject.utils import helper_function
from myproject.models import DataProcessor

# --- External Local Libraries (if applicable) ---
from shared_lib import common_utils
```

### Import Rules

| Rule | Example |
|------|---------|
| One import per line | `import os` (not `import os, sys`) |
| Alphabetize within groups | `import abc` before `import xyz` |
| Prefer absolute imports | `from myproject.utils import func` |
| Use relative imports sparingly | `from .sibling import func` (within same package only) |
| Never use wildcard imports | Avoid `from module import *` |

### Multi-line Imports

```python
from myproject.utils.modules import (
    first_function,
    second_function,
    third_function,
)
```

### Avoiding Circular Imports

**Strategy 1: Import at point of use (lazy import)**
```python
def get_user_data():
    from myapp.models import User  # Deferred import
    return User.objects.all()
```

**Strategy 2: TYPE_CHECKING guard for type hints**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myapp.models import User

def process_user(user: "User") -> None:
    pass
```

**Strategy 3: Extract shared code to a third module**
```python
# shared.py - Contains shared definitions
# module_a.py - Imports from shared
# module_b.py - Imports from shared (no circular dependency)
```

---

## The Law of Demeter

### Core Principle

An object should only communicate with its immediate collaborators. A method should only call methods of:

1. The object itself (`self`)
2. Objects passed as parameters
3. Objects created within the method
4. Direct attributes of the object

**Never call methods on objects returned by other method calls.**

### Violations and Fixes

**Violation: Train Wreck (Chain Calls)**
```python
# BAD - Violates Law of Demeter
def calculate_shipping(self, order):
    street = order.get_customer().get_address().get_street()
    zip_code = order.get_customer().get_address().get_zip_code()
    return self._calculate_for_location(street, zip_code)
```

**Solution: Delegate and Encapsulate**
```python
# GOOD - Proper delegation
def calculate_shipping(self, order):
    location = order.get_shipping_location()
    return self._calculate_for_location(location)

class Order:
    def get_shipping_location(self):
        return self._customer.get_shipping_address()
```

**Violation: Accessing Nested Attributes**
```python
# BAD
company_name = user.profile.company.name

# GOOD
company_name = user.get_company_name()
```

**Violation: Querying Object Internals**
```python
# BAD - Directly accessing internal collections
if len(invoice.line_items) > 0:
    total = sum([item.price * item.quantity for item in invoice.line_items])

# GOOD - Ask object for computed values
if invoice.has_items():
    total = invoice.calculate_total()
```

---

## Conditional Clarity

### Explicit Parentheses

Always use parentheses to clarify operator precedence in complex conditions:

```python
# UNCLEAR - Ambiguous precedence
if status == "active" and role == "admin" or permissions > 5:
    grant_access()

# CLEAR - Explicit precedence
if ((status == "active") and (role == "admin")) or (permissions > 5):
    grant_access()
```

### Explaining Variables

Extract complex conditions into named boolean variables:

```python
# BAD - Complex inline condition
if user.age >= 18 and user.is_active and any(p in user.permissions for p in required):
    allow_access()

# GOOD - Explaining variables
meets_age_requirement = (user.age >= 18)
is_active_user = user.is_active
has_required_permissions = any((p in user.permissions) for p in required)

if (meets_age_requirement and is_active_user and has_required_permissions):
    allow_access()
```

### Bitwise and Mixed Operators

```python
# Always parenthesize bitwise operations
result = (value & MASK) + OFFSET  # Not: value & MASK + OFFSET

# Mixed operators - make precedence explicit
if ((x > 10) and (y < 20)) or ((z == 0) and (w != 5)):
    process()
```

---

## Guard Clauses and Early Returns

### Pattern

Validate preconditions at the start of functions and return/raise immediately on failure:

```python
def process_order(order, inventory, payment_processor):
    # Guard clauses - validate early
    if (order is None):
        raise ValueError("Order cannot be None")

    if (not order.has_items()):
        raise ValueError("Order must contain items")

    if (not inventory.has_sufficient_stock(order)):
        raise ValueError("Insufficient stock for order")

    if ((payment_processor is None) or (not payment_processor.is_available())):
        raise ValueError("Payment processor unavailable")

    # Main logic - minimal indentation
    payment_result = payment_processor.charge(order.get_total())
    inventory.reserve_items(order)
    return payment_result
```

### Benefits

- Reduces nesting depth
- Makes preconditions explicit
- Simplifies main logic path
- Fails fast with clear error messages

---

## Code Organization Patterns

### Replace Magic Numbers with Constants

```python
# constants.py
LEGAL_DRINKING_AGE = 21
RETIREMENT_AGE = 65
TAX_RATE_STANDARD = 0.21
MILLISECONDS_PER_SECOND = 1000

# usage.py
from constants import LEGAL_DRINKING_AGE

def can_purchase_alcohol(age):
    return (age >= LEGAL_DRINKING_AGE)
```

### Use Enums for Magic Strings

```python
from enum import Enum, auto

class OrderStatus(Enum):
    PENDING = auto()
    PROCESSING = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()

class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"

# Usage
if (order.status == OrderStatus.PENDING):
    start_processing(order)
```

### Function Structure

```python
def well_structured_function(param1, param2, param3):
    """
    Brief description of function purpose.

    Args:
        param1: Description of param1
        param2: Description of param2
        param3: Description of param3

    Returns:
        Description of return value

    Raises:
        ValueError: When validation fails
    """
    # 1. Guard clauses / validation
    if (param1 is None):
        raise ValueError("param1 required")

    # 2. Setup / initialization
    result = []

    # 3. Main logic
    for item in param2:
        processed = _process_item(item, param3)
        result.append(processed)

    # 4. Return
    return result
```

---

## Avoiding Common Pitfalls

### Circular Import Prevention

| Strategy | When to Use |
|----------|-------------|
| Lazy import inside function | Quick fix; acceptable for rarely-called code |
| TYPE_CHECKING guard | Type hints only; no runtime dependency |
| Extract to shared module | Best long-term solution; proper separation |
| Restructure module hierarchy | When modules are too tightly coupled |

### Wildcard Import Problems

```python
# NEVER do this in production code
from module import *  # Pollutes namespace, hides origins

# ALWAYS be explicit
from module import specific_function, SpecificClass
```

### Deep Nesting

```python
# BAD - Deep nesting
def process(data):
    if data:
        if data.is_valid():
            if data.has_permission():
                if data.is_ready():
                    return do_work(data)
    return None

# GOOD - Guard clauses flatten structure
def process(data):
    if (not data):
        return None
    if (not data.is_valid()):
        return None
    if (not data.has_permission()):
        return None
    if (not data.is_ready()):
        return None

    return do_work(data)
```

### Composition over Inheritance

```python
# AVOID - Rigid inheritance hierarchy
class Animal:
    def move(self): pass

class FlyingAnimal(Animal):
    def fly(self): pass

class SwimmingAnimal(Animal):
    def swim(self): pass

# What about a duck that flies AND swims?

# PREFER - Composition with behaviors
class MovementBehavior:
    def move(self): pass

class FlyBehavior(MovementBehavior):
    def move(self):
        return "flying"

class SwimBehavior(MovementBehavior):
    def move(self):
        return "swimming"

class Duck:
    def __init__(self):
        self._fly_behavior = FlyBehavior()
        self._swim_behavior = SwimBehavior()

    def fly(self):
        return self._fly_behavior.move()

    def swim(self):
        return self._swim_behavior.move()
```

---

## Quick Reference Checklists

### Code Review Checklist

**Law of Demeter Violations:**
- [ ] Chain calls: `obj.method1().method2().method3()`
- [ ] Nested attribute access: `obj.attr1.attr2.attr3`
- [ ] Direct access to other objects' collections
- [ ] Querying internals instead of asking for behavior

**Conditional Clarity Issues:**
- [ ] Complex boolean expressions without parentheses
- [ ] Mixed `and`/`or` without grouping
- [ ] Missing explaining variables for complex logic
- [ ] Nested ternary expressions

**Import Issues:**
- [ ] Wildcard imports (`from x import *`)
- [ ] Imports not at top of file
- [ ] Imports not grouped/sorted
- [ ] Circular import potential

**General Issues:**
- [ ] Magic numbers in business logic
- [ ] String literals for status/type checking
- [ ] Deep nesting (>3 levels)
- [ ] Functions >30 lines without clear structure
- [ ] Negative boolean names (`is_not_valid`)

### Before/After Quick Reference

| Issue | Before | After |
|-------|--------|-------|
| Chain calls | `order.customer.address.city` | `order.get_shipping_city()` |
| Ambiguous condition | `a and b or c` | `(a and b) or c` |
| Magic number | `if age >= 21:` | `if (age >= LEGAL_AGE):` |
| Magic string | `if status == "active":` | `if (status == Status.ACTIVE):` |
| Wildcard import | `from os import *` | `from os import path, getcwd` |
| Deep nesting | Multiple nested `if` | Guard clauses with early return |

### Function Guidelines

| Metric | Guideline |
|--------|-----------|
| Length | Prefer <30 lines |
| Parameters | Prefer <5 parameters |
| Nesting depth | Maximum 3 levels |
| Return points | Use guard clauses; single main return |
| Responsibilities | One clear purpose |

---

## Summary

**Always:**
1. Use explicit parentheses in complex conditionals
2. Follow Law of Demeter - ask, don't reach
3. Replace magic values with constants/enums
4. Use guard clauses for early validation
5. Create explaining variables for complex logic
6. Organize imports properly (stdlib, third-party, local)
7. Apply SOLID, DRY, KISS, YAGNI principles

**Never:**
1. Chain multiple method calls accessing internals
2. Reach through objects to access nested attributes
3. Use wildcard imports
4. Rely on implicit operator precedence
5. Create deep nesting (>3 levels)
6. Write functions >30 lines without clear structure
7. Use negative boolean names

**Python-Specific:**
- Follow PEP 8 naming conventions
- Use `Enum` for magic strings
- Place constants in dedicated modules
- Prefer absolute imports over relative
- Use `TYPE_CHECKING` for type-hint-only imports
