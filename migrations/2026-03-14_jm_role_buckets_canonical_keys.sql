-- Migration: 2026-03-14 — JM campaign role_buckets_json canonical keys
-- Replace generic role_0..role_6 keys with canonical JM role taxonomy keys.
-- Campaign: Jungle Minds (id = 265703d9-774a-4041-9919-37fe2583e266)

UPDATE campaigns
SET role_buckets_json = '[
  {"key":"ux_lead","label":"UX Lead / Lead Designer","apollo_titles":["UX Lead","Lead UX Designer","Senior UX Lead","Lead UX/UI","Lead UX Research","Lead UX/UI Designer"],"weight":5.0},
  {"key":"ux_director","label":"UX Director / Head of UX","apollo_titles":["UX Director","Head of UX","Head of UX Design","Global User Experience Director","Global Lead of UX Design","Director of UX"],"weight":5.0},
  {"key":"product_design_lead","label":"Product Design Lead","apollo_titles":["Product Design Lead","Lead Product Designer","Head of Product Design","Principal Product Designer"],"weight":4.0},
  {"key":"lead_designer","label":"Lead Designer","apollo_titles":["Lead Designer","Design Lead","Senior Lead Designer"],"weight":4.0},
  {"key":"design_system","label":"Design System Lead / Engineer","apollo_titles":["Design System Lead","Design System Engineer","Design Systems Engineer","Design Systems Lead","Head of Design System"],"weight":4.0},
  {"key":"cx_lead","label":"CX Lead / E-Commerce Manager","apollo_titles":["CX Team Lead","Head of CX","Customer Experience Lead","E-Commerce Manager","Director Digital & Analytics"],"weight":2.0}
]'
WHERE id = '265703d9-774a-4041-9919-37fe2583e266';
