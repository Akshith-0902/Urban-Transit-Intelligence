# Business Requirements

## Project Type
End-to-end Data Analytics / Business Intelligence / Operations Analytics project.

## Business Scenario
Modeled on Chennai's Metropolitan Transport Corporation (MTC) — one of India's largest municipal bus networks. The authority operates a large fleet across hundreds of routes and faces:

1. Passenger demand that varies significantly through the day.
2. Overcrowding on some routes during peak periods.
3. Substantial unused capacity on other routes.
4. Delays concentrated on particular routes, stops, and time periods.
5. No unified view of demand and operational performance for management.
6. Bus-allocation decisions that are not sufficiently data-driven.
7. A fleet that is expensive to expand indefinitely — existing capacity must be used efficiently.

## Core Business Question
> How can the transport authority allocate buses and adjust service frequency to reduce passenger waiting time and overcrowding while maintaining efficient fleet utilization and controlling operating costs?

## Business Questions

### Passenger Demand
- How many passengers use the network, and which routes/stops see the highest volume?
- What are the busiest hours? How does demand differ weekday vs. weekend, and by season?
- Which routes have highly concentrated peak demand vs. consistently low demand?

### Operational Performance
- Which routes experience the most delay? What % of trips are on time?
- Which stops contribute to excessive journey times?
- How does actual journey time differ from scheduled?

### Capacity Utilization
- Which routes are overcrowded vs. underutilized?
- What is average/peak occupancy, and how does it change through the day?
- Which routes show the largest supply-demand mismatch?

### Geographic Analysis
- Which areas generate the most demand? Which are underserved?
- Which stops act as major hubs? Where are delays geographically concentrated?

### Resource Allocation
- Where should additional buses be deployed?
- Which low-utilization routes could release capacity?
- What is the estimated effect of moving buses between routes, or increasing peak-hour frequency?

### External Factors (optional / later phase)
- Does rainfall correlate with delays? Does traffic correlate with journey time?

## Scope

**In scope:** route/stop analysis, demand analysis, trip performance, delay analysis, bus utilization, peak-hour analysis, geographic visualization, route comparison, KPI calculation, interactive dashboard, operational recommendations, optional what-if simulation.

**Optional advanced scope (added only if it sharpens a decision):** demand forecasting, anomaly detection, weather/traffic integration, route clustering, optimization, scenario simulation, Streamlit app.

**Out of scope:** full scheduling software, real-time GPS control, passenger mobile apps, ticketing/payment processing, full route-planning software. This is an analytics and decision-support project, not a transit operations platform.

## Target Users

| User | Needs |
|---|---|
| Transport Operations Manager | Which routes are performing poorly, where delays occur, where to allocate buses |
| Planning Manager | Where demand is growing, which areas are underserved, where to invest |
| Finance / Management | Fleet efficiency, cost of service changes, improvements without buying more buses |
| Data Analyst | Reliable datasets, consistent KPIs, reproducible SQL/Python analysis, drill-down dashboards |

## Success Criteria

- [ ] Identify high-demand routes and stops
- [ ] Identify persistent overcrowding and underutilization
- [ ] Quantify route reliability (on-time rate, delay distribution)
- [ ] Identify major delay hotspots
- [ ] Analyze peak vs. off-peak demand
- [ ] Visualize geographic demand and delay patterns
- [ ] Explain key performance differences (root-cause, not just description)
- [ ] Provide evidence-backed operational recommendations
- [ ] Estimate the potential impact of proposed interventions
- [ ] Clearly document data sources and assumptions
- [ ] Reproduce the analysis through SQL/Python
- [ ] Present results through an interactive Power BI dashboard
