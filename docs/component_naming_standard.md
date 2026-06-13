# GearCity Component Naming Standard

A compact internal naming system for GearCity engines, chassis, and gearboxes/toolboxes.

The goal is to make component names short, readable, and useful during vehicle design without using cute vehicle-style names for internal parts.

## Quick Summary

Use short functional codes instead of model names.

| Component | Format                                  | Example      |
| --------- | --------------------------------------- | ------------ |
| Engine    | `[Role]-[Fuel]-[Layout/Power]-[Torque]` | `B-G-5P-40T` |
| Chassis   | `[Role]-[EngineBay]-[Weight]`           | `B-1210-330` |
| Gearbox   | `[Role]-[Gears][Type][OD]-[Torque]`     | `B-3M-55T`   |

Example balanced sedan set:

```text
Engine:  B-G-5P-40T
Chassis: B-1210-330
Gearbox: B-3M-55T
```

## General Principles

* Names should be short because GearCity has character limits.
* Naming should be positional, meaning each part of the name always has the same meaning.
* Component names should show practical information that matters during vehicle design.
* Do not include redundant information if it can already be inferred from role or component use.
* Do not include technology generation/version if the latest available technology is always used.
* Cute or branded names should be reserved for vehicles, not internal parts.
* No company prefix is needed because all components are internal.

## Role Codes

| Code | Role       | Meaning                                                                                       |
| ---- | ---------- | --------------------------------------------------------------------------------------------- |
| `E`  | Economy    | Cheap, efficient, reliable. Best for cheap/small cars.                                        |
| `B`  | Balanced   | Mainstream/general-purpose. Replaces "Standard."                                              |
| `L`  | Luxury     | Smooth, refined, expensive.                                                                   |
| `H`  | Heavy Duty | Durable, torquey, reliable. For pickups/vans/commercial vehicles.                             |
| `S`  | Sport      | Fast and sporty, but still usable/refined. Good for premium sports cars and sporty road cars. |
| `R`  | Racing     | Maximum performance focus with little concern for comfort/cost/practicality.                  |
| `A`  | Aircraft   | Aircraft engines if needed later.                                                             |
| `M`  | Marine     | Ship/marine engines if needed later.                                                          |

Important role-code decision:

Do not use `S` for Standard because `S` is more useful for Sport. Use `B` for Balanced/Mainstream instead. Ship engines use `M` for Marine.

Sport vs Racing:

* `S` = Sport: performance is very important, but refinement/luxury still matters.
* `R` = Racing: maximum performance; comfort, cost, and refinement are secondary.

## Fuel Codes

| Code | Fuel          |
| ---- | ------------- |
| `G`  | Gasoline      |
| `D`  | Diesel        |
| `LG` | Autogas / LPG |
| `85` | E85           |
| `E1` | Electric I    |
| `E2` | Electric II   |
| `E3` | Electric III  |
| `E4` | Electric IV   |
| `E5` | Electric V    |
| `NG` | Natural Gas   |
| `W`  | Water         |
| `H2` | Hydrogen      |
| `Y`  | Hybrid        |

Important fuel-code decisions:

* Hydrogen and Hybrid conflict if both use `H`.
* Use `H2` for Hydrogen.
* Use `Y` for Hybrid, from hYbrid.
* Heavy Duty Hybrid becomes `H-Y-...`
* Heavy Duty Hydrogen becomes `H-H2-...`
* Autogas should preferably be `LG` instead of `AG`, because `AG` could look like Aircraft Gasoline in compact names.

# Engine Naming

## Format

```text
[Role]-[Fuel]-[Layout/Power]-[Torque]
```

Example:

```text
E-G-5P-28T
```

Meaning:

| Part  | Meaning                                                                 |
| ----- | ----------------------------------------------------------------------- |
| `E`   | Economy role                                                            |
| `G`   | Gasoline                                                                |
| `5P`  | Engine layout/power/size code, depending on what is most useful in-game |
| `28T` | Torque                                                                  |

## Engine Role Details

### `E` — Economy

Cheap, efficient, reliable.

Use for:

* cheap cars
* small cars
* phaetons
* runabouts
* basic early cars

Does not care much about smoothness or luxury.

### `B` — Balanced

Mainstream/general-purpose engine.

Use for:

* sedans
* mainstream cars
* general family vehicles

Balanced cost, reliability, smoothness, and performance. Slight smoothness emphasis, but not luxury-level expensive.

### `L` — Luxury

Smooth, refined, expensive.

Use for:

* luxury sedans
* limousines
* premium cars

High smoothness is the main identity.

### `H` — Heavy Duty

Durable, torquey, reliable.

Use for:

* pickups
* vans
* trucks
* commercial vehicles

Can be heavier, rougher, and less smooth.

### `S` — Sport

Fast and sporty, but still usable and somewhat refined.

Use for:

* sports cars
* sporty coupes
* premium road cars
* grand touring style vehicles

Performance matters a lot, but unlike Racing, smoothness/luxury can still matter.

### `R` — Racing

Maximum performance focus.

Use for:

* racing
* future pure performance cars

Comfort, cost, reliability, and refinement are secondary.

### `A` — Aircraft

For airplane engines if/when needed later.

### `M` — Marine

For ship/marine engines if/when needed later.

## Engine Examples

| Name          | Meaning                       |
| ------------- | ----------------------------- |
| `E-G-5P-28T`  | Economy gasoline engine       |
| `B-G-5P-28T`  | Balanced gasoline engine      |
| `L-G-5P-28T`  | Luxury gasoline engine        |
| `H-G-5P-28T`  | Heavy-duty gasoline engine    |
| `S-G-6P-70T`  | Sport gasoline engine         |
| `S-85-6P-70T` | Sport E85 engine              |
| `S-Y-6P-70T`  | Sport hybrid engine           |
| `R-G-5P-28T`  | Racing gasoline engine        |
| `A-G-5P-28T`  | Aircraft gasoline engine      |
| `M-D-5P-28T`  | Marine diesel engine          |
| `H-H2-5P-28T` | Heavy-duty hydrogen engine    |
| `H-Y-5P-28T`  | Heavy-duty hybrid engine      |
| `H-NG-5P-28T` | Heavy-duty natural gas engine |
| `H-W-5P-28T`  | Heavy-duty water engine       |
| `E-LG-5P-28T` | Economy autogas/LPG engine    |
| `L-85-5P-28T` | Luxury E85 engine             |
| `B-E1-5P-28T` | Balanced Electric I engine    |

## Compact Engine Examples

If dashes need to be reduced:

| Compact      | Meaning                |
| ------------ | ---------------------- |
| `EG-5P-28T`  | Economy gasoline       |
| `BG-5P-28T`  | Balanced gasoline      |
| `HG-5P-28T`  | Heavy-duty gasoline    |
| `HH2-5P-28T` | Heavy-duty hydrogen    |
| `HY-5P-28T`  | Heavy-duty hybrid      |
| `HNG-5P-28T` | Heavy-duty natural gas |

Be careful with `LG-5P-28T` because it can be ambiguous:

* `L-G` could mean Luxury Gasoline
* `LG` could mean LPG/Autogas

Best practice:

Keep the first dash after the role if possible:

```text
H-H2-5P-28T
H-Y-5P-28T
E-LG-5P-28T
```

# Chassis Naming

Chassis names should not include exact vehicle type by default. Role, engine bay size, and weight should already communicate the practical use.

Chassis names should also not include suspension type by default. Suspension can usually be inferred from vehicle type/design era or inspected directly, and it is less important than weight and engine bay space.

## Most Important Chassis Information

* Role
* Engine bay length and width
* Chassis weight

## Format

```text
[Role]-[EngineBay]-[Weight]
```

Engine bay compression:

Use two 2-digit numbers for bay length and width, probably by dividing by 100.

| Engine Bay    | Compressed |
| ------------- | ---------- |
| `1000 x 1000` | `1010`     |
| `1200 x 1000` | `1210`     |
| `1400 x 1200` | `1412`     |
| `1300 x 1100` | `1311`     |

## Chassis Examples

| Name         | Meaning                                                |
| ------------ | ------------------------------------------------------ |
| `E-1010-204` | Economy chassis, 1000 x 1000 engine bay, 204 weight    |
| `B-1210-330` | Balanced chassis, 1200 x 1000 engine bay, 330 weight   |
| `L-1412-520` | Luxury chassis, 1400 x 1200 engine bay, 520 weight     |
| `H-1311-610` | Heavy-duty chassis, 1300 x 1100 engine bay, 610 weight |
| `R-1008-180` | Racing chassis, 1000 x 800 engine bay, 180 weight      |

Alternative readable version:

```text
E-10x10-204
B-12x10-330
L-14x12-520
H-13x11-610
```

Preferred version:

```text
E-1010-204
```

Reason:

It is shorter than using `x` but still readable.

# Gearbox / Toolbox Naming

Gearbox naming should focus on torque capacity because torque is one of the most important practical limitations for matching gearbox to engine.

Ratio behavior does not need to be named separately because it is usually implied by role:

* Economy gearbox likely has economy-focused gearing.
* Luxury gearbox likely emphasizes smoothness.
* Heavy Duty gearbox likely handles torque/hauling.
* Racing gearbox likely emphasizes performance/close ratios.

## Format

```text
[Role]-[Gears][Type][OD]-[Torque]
```

## Gearbox Type Codes

| Code | Meaning          |
| ---- | ---------------- |
| `M`  | Manual           |
| `A`  | Automatic        |
| `S`  | Semi-auto        |
| `O`  | Overdrive marker |

## Gearbox Examples

| Name        | Meaning                                                  |
| ----------- | -------------------------------------------------------- |
| `E-2M-30T`  | Economy 2-speed manual, 30 torque capacity               |
| `B-3M-55T`  | Balanced 3-speed manual, 55 torque capacity              |
| `L-3MO-70T` | Luxury 3-speed manual with overdrive, 70 torque capacity |
| `H-4M-120T` | Heavy-duty 4-speed manual, 120 torque capacity           |
| `R-4M-90T`  | Racing 4-speed manual, 90 torque capacity                |

Compact gearbox version:

```text
E2M30
B3M55
L3MO70
H4M120
R4M90
```

Preferred gearbox version:

```text
E-2M-30T
B-3M-55T
L-3MO-70T
H-4M-120T
```

Reason:

The dashes make it easier to parse while still staying short. The final `T` makes it obvious the last number is torque.

# Full Example Sets

## Cheap Economy Car / Phaeton Style

```text
Engine:  E-G-5P-28T
Chassis: E-1010-204
Gearbox: E-2M-30T
```

## Balanced Sedan

```text
Engine:  B-G-5P-40T
Chassis: B-1210-330
Gearbox: B-3M-55T
```

## Luxury Sedan / Limousine

```text
Engine:  L-G-6P-60T
Chassis: L-1412-520
Gearbox: L-3MO-70T
```

## Heavy-Duty Pickup / Van

```text
Engine:  H-D-5P-95T
Chassis: H-1311-610
Gearbox: H-4M-120T
```

## Heavy-Duty Hybrid

```text
Engine:  H-Y-5P-95T
Chassis: H-1311-610
Gearbox: H-4M-120T
```

## Heavy-Duty Hydrogen

```text
Engine:  H-H2-5P-95T
Chassis: H-1311-610
Gearbox: H-4M-120T
```

## Sport / Grand Touring

```text
Engine:  S-G-6P-70T
Chassis: S-1210-260
Gearbox: S-4MO-85T
```

Meaning:

* Sport gasoline engine
* Sport chassis with 1200 x 1000 engine bay and 260 weight
* Sport 4-speed manual with overdrive and 85 torque capacity

## Racing

```text
Engine:  R-G-5P-80T
Chassis: R-1008-180
Gearbox: R-4M-90T
```

# Conflict / Resolution Summary

* No company prefix is needed.
* Engine variation/generation does not need to be named because the latest tech is always used.
* Standard was renamed to Balanced because `S` is better used for Sport.
* Ship/marine engines use `M` for Marine.
* `S` means Sport: fast but still road-usable/refined.
* `R` means Racing: maximum performance with less concern for comfort/cost/practicality.
* Hydrogen should be `H2`.
* Hybrid should be `Y`.
* Heavy Duty remains `H`.
* Autogas should preferably be `LG` instead of `AG` to avoid conflicts with Aircraft Gasoline in compact names.
* Chassis should not include vehicle type or suspension unless there is a special reason.
* Chassis should include engine bay size and weight.
* Gearbox should include torque capacity.
* Cute names should be reserved for vehicles, not internal components.
