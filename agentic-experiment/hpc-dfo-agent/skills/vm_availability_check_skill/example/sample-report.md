  The live empirical VM availability test has completed across project  thomashk-mig  in zone  us-central1-a  on network  custom-
  network1  /  us-central1-subnet1-ip4 .

  The full empirical report is compiled in:
  📄 vm_availability_report.md
  ──────
  ### Empirical Live Deployment Results ( us-central1-a )

   VM Family | Tested Machine Type | Live Deploy… | Live GCP API Response           | Overall Status        | Rapid Cleanup Verified
  -----------|---------------------|--------------|---------------------------------|-----------------------|------------------------
   C2        |  c2-standard-4      | 5 / 5        | Created 5 instances             | ✅ Available          | Verified Deleted
             |                     |              | successfully                    |                       | (<30s)
   N2        |  n2-standard-4      | 5 / 5        | Created 5 instances             | ✅ Available          | Verified Deleted
             |                     |              | successfully                    |                       | (<30s)
   C4        |  c4-standard-4      | 5 / 5        | Created 5 instances             | ✅ Available          | Verified Deleted
             |                     |              | successfully                    |                       | (<30s)
   C2D       |  c2d-standard-4     | 0 / 5        |  ZONE_RESOURCE_POOL_EXHAUSTED   | ⚠️ Stockout in Zone A | N/A (0 active)
   C3        |  c3-standard-4      | 1 / 5        |  ZONE_RESOURCE_POOL_EXHAUSTED   | ⚠️ Partial Stockout   | Verified Deleted
   C4D       |  c4d-standard-4     | 0 / 5        |  ZONE_RESOURCE_POOL_EXHAUSTED   | ⚠️ Stockout in Zone A | N/A (0 active)
   N4        |  n4-standard-4      | 0 / 5        |  ZONE_RESOURCE_POOL_EXHAUSTED   | ⚠️ Stockout in Zone A | N/A (0 active)
   H4D       |  h4d-standard-16    | 0 / 5        | Machine type not present in     | ⚠️ Zone Unavailable   | N/A (0 active)
             |                     |              | us-central1-a                   |                       |
  ──────
  ### Key Recommendations

  1. Production Deployment Choice:  C2 ,  N2 , and  C4  are fully stocked and available in  us-central1-a  (100% 5/5 creation 
  success).
  2. Alternative Zones for  C2D  /  C3  /  C4D  /  N4 : Due to high demand in  us-central1-a , deploy these families in neighboring
  zones ( us-central1-b ,  us-central1-c , or  us-central1-f ).
  3. Zero Cost Assurance: Every created instance was automatically purged in under 30 seconds. Zero test instances remain active in
  your project.
