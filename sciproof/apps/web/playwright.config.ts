import {defineConfig} from '@playwright/test';
import {resolve} from 'node:path';
export default defineConfig({
  testDir:'./e2e',fullyParallel:false,workers:1,retries:0,timeout:120000,
  expect:{timeout:30000},
  reporter:[['list'],['json',{outputFile:resolve(__dirname,'../../.runtime/e2e-results.json')}]],
  use:{baseURL:'http://localhost:3000',browserName:'chromium',viewport:{width:1440,height:1000},
       trace:'off',screenshot:'only-on-failure'},
});
