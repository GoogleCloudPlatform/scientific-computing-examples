#
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "sm11_files_small" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/F2CC2199-4492-E411-AD13-00266CFFA6F8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/F44F8968-6592-E411-8168-0025901D4936.root",
  ]
}

variable "sm11_files_medium" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/0A571FF3-6392-E411-AB3D-0025904B12FC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/0C7108A5-4892-E411-A91F-002590AC4C6E.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/122F5808-4F92-E411-BCBE-003048F0E518.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/16FCDFCB-6992-E411-B526-00259081A24A.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/2E0071DB-4892-E411-A3EA-0025907FD24A.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/301C8BBD-4292-E411-A188-0025904B12A8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/30612C4A-6692-E411-AE7C-0025904B12A8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/30B3A221-4992-E411-8282-002590DB046C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/349665AF-5C92-E411-B1E7-0025904B1424.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/34D10D41-6F92-E411-9505-002590DB9214.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/40E40D19-5092-E411-BBAE-0025901D4C94.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/469A16C7-6492-E411-87D6-0025901D4926.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/46C4D56E-5692-E411-B6A2-00266CFFA124.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/487A6B0A-5E92-E411-88AD-0025904B1372.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/4A7274EF-6192-E411-8554-0025904B1446.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/4C524C57-6392-E411-9537-0025904B12A4.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/4C849F63-6D92-E411-A75E-002590DB05F4.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/507A89F2-5E92-E411-BB37-00266CFFA0B0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/5416D41A-5192-E411-9FCA-00266CFFA124.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/54F2A2BC-7292-E411-A831-002590AC4B1A.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/5A89CDD9-6F92-E411-9F4C-0025904B12A8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/66312CAF-6E92-E411-B382-003048F0E7FC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/6A50AF33-4E92-E411-8945-0025907DCA72.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/6CB8AE06-4992-E411-81E3-002590494CB2.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/6E0345E4-5A92-E411-85A3-0025901D4940.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/720CB670-4B92-E411-A25D-003048D439BE.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/723CEA7F-3C92-E411-9907-0025904B12A4.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/76BE8381-5C92-E411-AF9B-0025901D4124.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/783AB85D-4B92-E411-AEB6-00266CFFA2EC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/7847EA20-4992-E411-A24B-00259081A2C8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/78515F6D-5F92-E411-A89D-0025904B12F0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/7EFD15F5-5A92-E411-A758-0025901D4124.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/8C5BF93F-5292-E411-B05F-003048F0E836.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/9229653B-4E92-E411-A8A8-003048F0E518.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/96F27D81-6892-E411-85D2-00259081A2C8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/A0EFDAF1-4392-E411-AED7-00266CFFA204.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/A6C2549A-6192-E411-84F3-002590AB38DA.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/ACA6BD13-6392-E411-B457-0025907DC9D0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/B268364B-4F92-E411-8A48-002481E0DDE8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/B6186B01-5B92-E411-A43E-00266CF330B8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/B6CA79CC-4292-E411-A149-00266CF326A8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/BAFF5570-2592-E411-974C-00266CF2718C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/C04FCBA7-4592-E411-9EED-0025907DC9C4.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/C42CD5BD-4393-E411-B690-002590DB9232.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/C84C7F31-3092-E411-AED3-00266CF32F18.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/D0526DE2-5A92-E411-B2C2-0025904B1026.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/D0AAA6C7-4892-E411-A42D-002481E0DC66.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/D4803EB0-2A92-E411-B9A7-0025904B1364.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/D6A30702-5492-E411-B90C-002481E76372.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/D6E49068-4692-E411-B804-003048D438EA.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/DC3767CD-4892-E411-8931-00266CFFA5CC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/DE305246-4E92-E411-88DB-00266CF32E78.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/DEA47FB6-4B92-E411-960F-00266CFFA750.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/DEAEBEEF-7892-E411-9E85-0025904B12DE.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/E0769066-7592-E411-829E-0025904B1026.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/E231A6C9-7192-E411-8680-00266CFFA2C4.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/E42A7A37-4E92-E411-97C3-002481E0DAB0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/E6E12B7C-4E92-E411-8219-002481E0DDE8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/ECDF9F7B-3692-E411-B18F-00266CF2AE10.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/EE7A35CB-7792-E411-A7FB-00266CF327E0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/F22CD811-6092-E411-ADDE-00266CF33318.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/F2CC2199-4492-E411-AD13-00266CFFA6F8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2011/Summer11LegDR/ZZTo2e2mu_mll4_7TeV-powheg-pythia6/AODSIM/PU_S13_START53_LV6-v1/00000/F44F8968-6592-E411-8168-0025901D4936.root",
  ]
}

variable "sm12_files_small" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/F01FC321-61D9-E211-8A71-00266CFFCD6C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/F8333E82-64D9-E211-8DF3-00266CFEFDEC.root",
  ]
}

variable "sm12_files_medium" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/029D759D-6CD9-E211-B3E2-1CC1DE041FD8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/02A8CA7F-52D9-E211-9260-1CC1DE1D1F80.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/0824586C-4CD9-E211-87B3-1CC1DE041FD8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/22FD6176-5ED9-E211-818D-AC162DACE1B8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/24DB66A2-4DD9-E211-BAE1-00266CFEFC38.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/281F76A2-23D9-E211-BB68-1CC1DE04FF50.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/28CDF98C-43D9-E211-ADB8-00266CFFCAC0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/32C0B5E3-5BD9-E211-B275-1CC1DE1CDF2A.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/387184FD-4DD9-E211-A8CC-00266CFFBF64.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/3C72440D-60D9-E211-87B8-008CFA052A88.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/421ABD63-51D9-E211-81B4-AC162DA87230.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/42D7D08F-45D9-E211-9754-00266CFFCD60.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/5623F7A5-67D9-E211-83A2-1CC1DE05B0C8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/5E1BF8AC-64D9-E211-87D9-008CFA0527CC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/640458BB-48D9-E211-8684-78E7D1E49636.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/72F33A13-66D9-E211-A928-00266CFEFDEC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/7C717FB0-38D9-E211-9D3B-00266CFFC9EC.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/86AF48A1-68D9-E211-9E4C-00266CFFBED8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/8C00288B-57D9-E211-AA17-D485645C8BC8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/942A698C-47D9-E211-8E87-1CC1DE052068.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/9689388B-4FD9-E211-91ED-1CC1DE04FF48.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/9A28FC69-50D9-E211-94D5-00266CFFCB14.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/9A5F5551-51D9-E211-99B2-00266CFFC51C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/AC79DD3E-55D9-E211-95D5-1CC1DE1D14A0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/BE525F74-53D9-E211-AB10-00266CFE6404.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/C4956C23-67D9-E211-BE12-AC162DA87230.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/CA308B89-4BD9-E211-9175-AC162DACC3E8.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/CABC0B0A-73D9-E211-B2C9-00266CFFC940.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/DC9542DD-55D9-E211-898A-00266CFFCD6C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/DCA5DF96-4ED9-E211-8AED-1CC1DE046F78.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/EAF03D95-75D9-E211-84D6-1CC1DE04FF98.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/EE8E8C06-73D9-E211-8FF9-1CC1DE046FC0.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/F01FC321-61D9-E211-8A71-00266CFFCD6C.root",
    "gs/higgs-tutorial/eos/opendata/cms/MonteCarlo2012/Summer12_DR53X/SMHiggsToZZTo4L_M-125_8TeV-powheg15-JHUgenV3-pythia6/AODSIM/PU_S10_START53_V19-v1/10000/F8333E82-64D9-E211-8DF3-00266CFEFDEC.root",
  ]
}

variable "cmsrun_input_files_small" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/F2878994-766C-E211-8693-E0CB4EA0A939.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/FA6ED8D4-616C-E211-AC71-20CF305B050B.root",
  ]
}

variable "cmsrun_input_files_medium" {
  type = list(string)
  default = [
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/20000/1070A5BE-B766-E211-A459-20CF3027A5E2.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/20000/189B37E5-C166-E211-97F9-E0CB4E19F983.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/20000/24C9FA82-5466-E211-AA29-485B39800C16.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/20000/98EBF5A8-4C66-E211-8D0B-485B39800B9D.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/00A78F44-296D-E211-9DE9-20CF305B0535.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/20CC4625-CE6D-E211-9FD9-00261834B55C.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/58D6D152-A16D-E211-A6C1-001EC9D2577D.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/6E548567-D66D-E211-B3FA-90E6BA442EF6.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/749CA4CA-296D-E211-A078-001EC9D7F21F.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/84C75D55-5B6C-E211-9F2B-E0CB4E19F9B5.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/8C86820D-2A6D-E211-B467-E0CB4E553667.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/9AFBA41E-AB6C-E211-ADE2-E0CB4E1A115D.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/CAC93CCF-276D-E211-951A-BCAEC532972B.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/CEB2B52F-DA6C-E211-A7E0-00259073E398.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/E89325B1-9D6C-E211-81A9-001EC9D80771.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/F028D8BE-D66C-E211-AE14-E0CB4E1A1194.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/F2878994-766C-E211-8693-E0CB4EA0A939.root",
    "gs/higgs-tutorial/eos/opendata/cms/Run2012C/DoubleMuParked/AOD/22Jan2013-v1/10000/FA6ED8D4-616C-E211-AC71-20CF305B050B.root",
  ]
}

variable "cmsrun_luminosity_data_small" {
  type = list(string)
  default = [
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
  ]
}

variable "cmsrun_luminosity_data_medium" {
  type = list(string)
  default = [
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
    "{\"stream\": \"mu_stream_2012\", \"value\": 178306109.36379963}",
  ]
}
