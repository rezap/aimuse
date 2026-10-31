// End-to-end check of the whole app on the emulators (fake engine, no cost):
// sign in -> make a song -> wait for it in the library -> audio downloads -> rating saves.
// Run via scripts/e2e.sh (starts the emulators and the web app first).
import { chromium } from "playwright";

const base = process.env.APP_URL ?? "http://localhost:3000";
const shots = process.env.SHOTS_DIR;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
const shot = (name) => shots && page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
try {
  await page.goto(base);
  await page.getByRole("button", { name: "Test user (emulator)" }).click();
  await page.getByText("Make a song").waitFor({ timeout: 30000 });
  await page.getByRole("radio", { name: /Late Night Lo-fi/ }).click();
  await page.getByRole("button", { name: "calm", exact: true }).click();
  await page.locator("#theme").fill("rain on a neon city");
  await page.locator("#inspiration").fill("Bob Dylan");
  await shot("1-composer");
  await page.getByRole("button", { name: "Make it" }).click();
  await page.locator("li.track audio").first().waitFor({ timeout: 180000 });
  const head = await page.locator("li.track .track-head").first().innerText();
  if (!head.includes("Rain on a neon city")) throw new Error(`unexpected track: ${head}`);
  const src = await page.locator("li.track audio").first().getAttribute("src");
  const audio = await page.request.get(src);
  if (audio.status() !== 200 || (await audio.body()).length < 10000) {
    throw new Error(`audio download failed: ${audio.status()}`);
  }
  const influence = await page.locator("li.track .influence").first().innerText();
  if (!influence.includes("In the spirit of Bob Dylan") || !influence.includes("folk rock")) {
    throw new Error(`artist style not shown: ${JSON.stringify(influence)}`);
  }
  // The artist's description includes who sings (this first song is instrumental, so no voice).
  if (!influence.includes("male lead singer")) {
    throw new Error(`artist singer not described: ${JSON.stringify(influence)}`);
  }
  await page.locator("li.track summary", { hasText: "Lyrics" }).first().click();
  const lyrics = await page.locator("li.track .lyrics").first().innerText();
  if (!lyrics.includes("Fake engine sings softly") || lyrics.includes("[0.0")) {
    throw new Error(`lyrics not cleaned up: ${JSON.stringify(lyrics)}`);
  }
  await page.getByRole("button", { name: "👍" }).first().click();
  await page.locator('button[aria-pressed="true"]').first().waitFor({ timeout: 10000 });
  await shot("2-library");

  // Second song from the listener's own lyrics.
  await page.getByRole("button", { name: /Use my own lyrics/ }).click();
  await page.locator("#lyrics").fill("Paper boats on a silver stream\nCarry every little dream\n\nLet them sail into the light");
  await page.getByRole("button", { name: "Female", exact: true }).click();
  await page.getByRole("button", { name: "Make it" }).click();
  const boats = page.locator("li.track", { hasText: "Paper boats on a silver stream" });
  await boats.waitFor({ timeout: 180000 });
  if (!(await boats.innerText()).includes("female voice")) {
    throw new Error("the listener's singer choice was not used");
  }
  await shot("3-own-lyrics");
  console.log(`E2E OK: ${head.replace(/\n/g, " | ")}`);
} catch (e) {
  await shot("failure");
  console.error(`E2E FAILED: ${e.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
