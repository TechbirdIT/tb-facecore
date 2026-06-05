# Competitor Feature Benchmark + Pricing — Face-Recognition Attendance (2026-06-05)

Scope: benchmark for a custom Frappe HRMS-coupled face attendance app (self-hosted B2B, edge devices with IP cameras posting recognition events to a Frappe server, employee self-service registration portal). Target: India-first SMB/mid-market, global later.

Note on data quality: most India HRMS vendors gate exact pricing behind sales/demos. Figures below are drawn from vendor pages plus third-party aggregators (Techjockey, SoftwareSuggest, Capterra, HRSuggest) and may lag actual quotes. Treat per-employee numbers as directional.

## Competitor matrix

| Vendor | Category | Liveness / anti-spoof | Multi-camera | Mobile check-in | Geofencing | Offline mode | Reports | Payroll integration | Deployment | Hardware |
|---|---|---|---|---|---|---|---|---|---|---|
| [Truein](https://truein.com/face-recognition-attendance-machine-price-in-india/) | Dedicated face/T&A SaaS | Yes (photo/video spoof alerts, auto-deactivation) | App-per-device (tablet kiosks) | Yes (Android/iOS) | Yes (advanced, day-wise policies) | Yes (offline sync) | Yes (timesheets) | Yes (export + integrations) | Cloud | Hardware-free; any phone/tablet |
| [OLOID](https://www.oloid.com/authentication-factors/face) | Workforce auth + T&A | Yes (liveness, SOC2 Type 2) | Tablet/kiosk clocks (3,500-unit deployments) | Yes (multi-platform) | Limited (auth-focused) | Backup codes/QR; cloud-centric | Yes | Yes (ADP, Workday Gold partner) | Cloud | Off-the-shelf tablets/webcams |
| [Keka](https://www.techjockey.com/detail/keka-hris) | Full HRMS + kiosk face | Yes (liveness on supported devices) | Kiosk app (shared tablets) | Yes | Yes | Limited (device-dependent) | Yes (full HR analytics) | Native (own payroll) | Cloud | Tablet/phone kiosk |
| [greytHR (Visage)](https://www.greythr.com/pricing/) | HRMS + face add-on | Yes (AI proxy prevention) | Add-on | Yes | Yes (GeoMark+ add-on) | Limited | Yes | Native (own payroll) | Cloud | Phone/tablet |
| [Zoho People](https://www.zoho.com/people/) | HRMS + face check-in | Liveness only on TrueDepth-capable devices | App-based | Yes | Yes | Limited | Yes | Native (Zoho Payroll) | Cloud | Phone/tablet |
| [factoHR](https://factohr.com/attendance-management-system/) | HRMS + face/kiosk | Yes (AI proxy-punch prevention) | Kiosk mode | Yes (GPS/selfie punch) | Yes | Limited (Azure cloud) | Yes | Native (own payroll) | Cloud (Azure) | Phone/tablet kiosk |
| [Matrix COSEC ARGO FACE](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/) | Hardware terminal + platform | Yes (dual-cam IR liveness, ~99.53%) | Per-terminal; centralized server | Yes (BLE/QR/location) | Yes (mobile) | Yes (standalone mode, on-device events) | Yes (CENTRA TAM) | Yes (API/export) | On-prem + cloud | Proprietary terminal (50k users, 200k templates) |
| [Hikvision / CP Plus](https://www.hikvision.com/) | Hardware terminals | Yes (IR/depth liveness on higher models) | Per-terminal; VMS/HikCentral | Limited | No (fixed terminal) | Yes (on-device storage) | Via platform/API | Via API (5 integration methods) | On-prem (terminal + server) | Proprietary terminal (₹3.6k–higher) |
| [AMS / Matrix COSEC](https://www.matrixcomsec.com/solution/time-attendance-solution/) | Enterprise T&A platform | Yes (terminal-level) | Multi-site centralized | Yes | Yes | Yes | Yes (centralized) | Yes | On-prem + cloud | Terminal + server software |
| [uKnowva](https://uknowva.com/hrms/virtual-biometric) | HRMS + "virtual biometric" | Weak (no confirmed dedicated face liveness) | App-based | Yes | Yes (location master + radius) | Limited | Yes | Native | Cloud | Phone (Google Maps API) |
| [FaceFirst](https://www.facefirst.com/) | Enterprise FR platform (security-first) | Yes (dual-algorithm w/ ROC) | Yes (multi-camera video analytics) | No (security/surveillance focus) | No | On-prem capable | Yes (analytics) | Via SDK/API | Cloud + on-prem | Existing cameras + SDK |

Observations:
- Two archetypes dominate: (a) cloud HRMS suites with software face check-in via phone/tablet (Keka, greytHR, Zoho, factoHR, uKnowva, Truein, OLOID); (b) hardware-terminal players with on-prem servers (Matrix COSEC, Hikvision, CP Plus). FaceFirst is a security/surveillance outlier.
- Almost nobody in the cloud-SaaS group offers a true edge-device + IP-camera + on-prem-server model. The hardware players do on-prem but with proprietary closed terminals, not open IP cameras. Our architecture sits in a relatively uncrowded middle: open IP cameras + self-hosted server + HRMS coupling.

## Table-stakes features

Baseline that virtually every serious 2026 entrant ships; absence is a deal-breaker:

- Face match check-in/out with sub-second 1:N matching ([Matrix](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/)).
- Liveness / anti-spoofing against photo and video replay ([Truein](https://truein.com/blogs/biometric-attendance-system), [Matrix](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/)).
- Proxy/buddy-punch prevention ([factoHR](https://factohr.com/attendance-management-system/), [OLOID](https://www.oloid.com/authentication-factors/face)).
- Mobile/tablet check-in (Android + iOS) ([Truein](https://truein.com/mobile-based-attendance-system)).
- Geofencing for location-bound punches ([factoHR](https://factohr.com/attendance-management-system/), [uKnowva](https://docs.uknowva.com/hr-and-admin/leaves-and-attendance/attendance/259-how-to-setup-a-geo-fence-in-uknowva)).
- Attendance reports + timesheets, exportable ([Truein](https://truein.com/mobile-based-attendance-system)).
- Payroll integration / payroll-ready timesheets ([Keka](https://www.techjockey.com/detail/keka-hris), [greytHR](https://www.greythr.com/pricing/)).
- Shift/policy rule engine (late marks, OT, breaks, holidays) ([Truein](https://truein.com/face-recognition-attendance-machine-price-in-india/), [factoHR](https://factohr.com/attendance-management-system/)).
- Employee self-service portal (payslips, leave, attendance view) ([factoHR](https://factohr.com/attendance-management-system/)).
- Indian statutory compliance (labour law, tax filings) for the India market ([factoHR](https://factohr.com/attendance-management-system/)).
- Privacy-by-design template storage (store embedding, discard image) ([OLOID](https://www.oloid.com/blog/advancing-security-with-facial-based-authentication)).
- Offline operation with auto-sync on reconnect ([Truein](https://truein.com/blogs/biometric-attendance-system), [Matrix standalone mode](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/)).

## Differentiators

Features that separate leaders or open whitespace in 2026:

- True on-prem / self-hosted data control with open IP cameras (not proprietary terminals). Hardware players do on-prem but locked to their devices; cloud SaaS can't do on-prem at all. This is our core wedge.
- Hardware-grade IR/depth liveness at ~99.5% on dual-camera terminals ([Matrix ARGO FACE](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/)) vs. RGB-only liveness on commodity phones — depth/IR remains a quality moat.
- Self-service / zero-touch enrollment (employees onboard via secure link or HRIS bulk sync) ([OLOID onboarding](https://www.oloid.com/authentication-factors/face)).
- Adaptive enrollment that absorbs facial changes without re-enroll ([Matrix](https://attendancemachine.in/products/matrix-cosec-argo-facee)).
- Recognition with masks/beards/accessories ([Truein](https://truein.com/face-recognition-attendance-machine-price-in-india/)).
- Deep HRIS/payroll certification (ADP/Workday Gold partner) ([OLOID](https://www.oloid.com/integrations/oloid-adp-integration)) — for global expansion.
- High template/event capacity for large multi-site deployments (50k users / 500k events per terminal) ([Matrix](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/)).
- Multi-camera video-analytics scale + dual-algorithm matching for accuracy/fairness ([FaceFirst + ROC](https://www.gatekeepersystems.com/resources/insights/facefirst-roc-improving-responsible-retail-ai/)).
- Device fleet health/heartbeat monitoring — rarely marketed explicitly by competitors; a credible differentiator for distributed edge fleets.

## Pricing landscape

| Vendor | Model | Published price (INR where available) | Notes |
|---|---|---|---|
| [Truein](https://www.techjockey.com/detail/truein-face-attendance) | Per user/year + setup | ~₹350–390/user/yr (resellers); ~₹69,000 base setup/yr; plans Capture/Advance/Enterprise | Official site quote-based; reseller figures may be dated |
| [Keka](https://www.hrsuggest.com/resources/keka-pricing-india) | Per-100-employee tiers | ~₹9,999 / ₹12,999 / ₹15,999 per month per 100 emp (Foundation/Strength/Growth); ~₹89–99 PEPM; +~₹150/emp beyond 100 | 25-emp billing floor; implementation/add-on fees push effective cost 35–55% higher |
| [greytHR](https://www.greythr.com/pricing/) | Base + PEPM, face = add-on | Essential ₹3,495/mo +₹35/emp (no attendance); Growth ₹5,495/mo (attendance); Enterprise ₹7,495/mo; +₹85 PEPM above 50; Visage face = add-on (quote) | Free Starter ≤25 emp; face attendance needs Growth+ plus Visage |
| [factoHR](https://www.techjockey.com/detail/factohr) | Per employee/month | Not public; starting package ~₹14,997 (Techjockey listing) | Quote-based; free trial |
| [uKnowva](https://uknowva.com/leaveandattendance/) | Per user/month | ~₹100/user/mo (Full Edition incl. ESS, leave/attendance, payroll) | Virtual biometric, not confirmed dedicated face |
| [Matrix COSEC](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/) | Hardware capex + platform | Terminal capex (quote); CENTRA platform licensing | Per-terminal hardware spend; on-prem |
| [Hikvision / CP Plus](https://www.indiamart.com/) | Hardware capex | ~₹3,600–4,500+/unit (entry); higher for 50k-face/temp models | Per-terminal; reseller pricing on IndiaMART/Amazon |
| [OLOID](https://www.oloid.com/) | Enterprise quote | Not public | Sold via ADP marketplace / enterprise |
| [FaceFirst](https://www.facefirst.com/) | Enterprise quote | Not public (custom) | Security/retail enterprise |
| [Zoho People](https://www.zoho.com/people/) | Per user/month | Not captured in this round (Zoho publishes tiered PEPM) | Native Zoho Payroll integration |

Pricing patterns:
- SaaS HRMS: ~₹89–100 PEPM is the India SMB benchmark (Keka, uKnowva), often with base fees and employee-slab jumps.
- Dedicated face SaaS (Truein): low per-user/year (~₹350–390) but a sizeable annual base/setup fee — favours larger headcounts.
- Hardware (Matrix/Hikvision/CP Plus): capex per terminal, no PEPM — attractive for fixed-location single-site, expensive to scale across sites.
- Face recognition is frequently an add-on (greytHR Visage), not bundled — a packaging cue.

## Market size

- Face Recognition Attendance System segment (specific): USD 3.5B (2024) → USD 10.2B (2033), ~15.8% CAGR ([Verified Market Reports](https://www.verifiedmarketreports.com/product/face-recognition-attendance-system-market/)).
- Broader global facial recognition market: ~USD 10B in 2026, ~14.7%–17.2% CAGR to 2031–2035 ([Mordor](https://www.mordorintelligence.com/industry-reports/facial-recognition-market), [Fortune Business Insights](https://www.fortunebusinessinsights.com/industry-reports/facial-recognition-market-101061)).
- Time & attendance software market (all biometrics): ~USD 4B in 2025–26, ~7.4%–11% CAGR ([Mordor](https://www.mordorintelligence.com/industry-reports/time-and-attendance-software-market), [MarkNtel](https://www.prnewswire.com/news-releases/global-time-and-attendance-software-market-to-reach-usd-6-32-billion-by-2032--growing-at-a-cagr-of-7-35-reports-markntel-advisors-302726110.html)).
- India: high-growth but estimates diverge widely — ~8.7% CAGR ([IMARC](https://www.imarcgroup.com/india-facial-recognition-market)) to ~16.5% ([Statista](https://www.statista.com/outlook/tmo/artificial-intelligence/computer-vision/facial-recognition/india)) to ~25% ([Grand View](https://www.grandviewresearch.com/horizon/outlook/facial-recognition-market/india)). Asia-Pacific is the fastest-growing region (~22% CAGR), with India + China leading adoption ([Mordor](https://www.mordorintelligence.com/industry-reports/facial-recognition-market)).

Takeaway: contactless face attendance is a clear secular tailwind (~16% CAGR niche), India among the fastest adopters, partly government-mandate-driven.

## Implications for our product

Our current capabilities: face-match attendance events, employee self-registration portal, approval workflow, offline edge queue, RTSP/IP camera support, device heartbeat monitoring, HRMS check-in integration.

Where we are differentiated / strong:
- Self-hosted + open IP cameras: genuinely uncommon. Cloud SaaS can't offer on-prem; hardware players lock you to proprietary terminals. Our edge + IP-camera + self-hosted Frappe server is a real wedge for data-sovereignty-sensitive India buyers (BFSI, govt, defence-adjacent, large manufacturing).
- Offline edge queue: matches Truein/Matrix table stakes — we are not behind here.
- Device heartbeat monitoring: most competitors don't market fleet health at all; lean into this for multi-site ops.
- Employee self-registration portal + approval workflow: matches OLOID's self-service/assisted onboarding; ahead of hardware players who require admin enrollment at the terminal.
- HRMS check-in integration: deep native coupling to Frappe HRMS is our equivalent of Keka/greytHR native payroll — strong for the Frappe/ERPNext install base.

Gap list (priority order):

1. Liveness / anti-spoofing depth. Confirm and market our liveness story. Commodity RGB liveness is table stakes; hardware rivals tout IR/dual-cam ~99.5%. If we run RGB-only, document accuracy and consider supporting depth/IR cameras on the edge. (vs. [Matrix](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/), [Truein](https://truein.com/blogs/biometric-attendance-system))
2. Mobile app check-in. Competitors universally offer Android/iOS phone punch with selfie + GPS. We are camera/edge-centric; a mobile self-punch path for field/remote staff is a notable gap. (vs. [Truein](https://truein.com/mobile-based-attendance-system), [factoHR](https://factohr.com/attendance-management-system/))
3. Geofencing. Standard everywhere for distributed teams; pairs with #2. Not in our listed feature set. (vs. [factoHR](https://factohr.com/attendance-management-system/), [uKnowva](https://docs.uknowva.com/hr-and-admin/leaves-and-attendance/attendance/259-how-to-setup-a-geo-fence-in-uknowva))
4. Shift / policy rule engine. Truein advertises 70+ policies; rich late/OT/break/holiday rules are expected mid-market. Verify our Frappe HRMS coverage suffices. (vs. [Truein](https://truein.com/face-recognition-attendance-machine-price-in-india/))
5. Payroll-ready reporting / timesheets. Ensure attendance events roll into Frappe payroll cleanly with exportable timesheets. (vs. [Keka](https://www.techjockey.com/detail/keka-hris), [greytHR](https://www.greythr.com/pricing/))
6. Indian statutory compliance packaging. Market explicit labour-law/compliance coverage as factoHR does. (vs. [factoHR](https://factohr.com/attendance-management-system/))
7. Privacy-by-design messaging. State that we store embeddings and discard raw images (OLOID's selling point); strong for India DPDP-era buyers. (vs. [OLOID](https://www.oloid.com/blog/advancing-security-with-facial-based-authentication))
8. Recognition robustness (masks/beards/accessories) and adaptive re-enrollment — verify and benchmark. (vs. [Truein](https://truein.com/face-recognition-attendance-machine-price-in-india/), [Matrix](https://attendancemachine.in/products/matrix-cosec-argo-facee))
9. Scale/capacity numbers. Competitors publish 50k users / 200k templates / 500k events. Publish our per-edge and per-server capacity to compete in mid-market RFPs. (vs. [Matrix](https://www.matrixcomsec.com/product/cosec-argo-face-door-controllers/))
10. Pricing/packaging clarity. India SMB anchors at ~₹89–100 PEPM (SaaS) or per-terminal capex (hardware). Define whether we price per-employee, per-camera/edge, or flat self-hosted license — our self-hosted model can undercut PEPM SaaS on TCO at scale; make that explicit.
