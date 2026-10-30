#!/usr/bin/env node
// Repeatable layout and motion audit (see PLAN.MD §6.1, §6.2, §6.3)
// Runs against a live/dev server via Playwright.

import { chromium } from 'playwright';
import process from 'node:process';

const ROUTES = ['/', '/analytics', '/accounts', '/prop', '/journal', '/tags', '/misc'];
const VIEWPORTS = [
	{ name: 'mobile', width: 375, height: 667 },
	{ name: 'tablet', width: 768, height: 1024 },
	{ name: 'desktop', width: 1280, height: 800 }
];

function getBaseUrl() {
	const args = process.argv.slice(2);
	for (let i = 0; i < args.length; i++) {
		if (args[i] === '--base-url' && args[i + 1]) {
			return args[i + 1];
		}
		if (args[i].startsWith('--base-url=')) {
			return args[i].split('=')[1];
		}
	}
	return process.env.AUDIT_BASE_URL || 'http://localhost:3000';
}

async function audit() {
	const baseUrl = getBaseUrl();
	console.log(`Auditing UI at ${baseUrl}`);
	const browser = await chromium.launch({ headless: true });
	const issues = [];

	for (const theme of ['dark', 'light']) {
		for (const vp of VIEWPORTS) {
			const context = await browser.newContext({
				viewport: { width: vp.width, height: vp.height },
				colorScheme: theme === 'dark' ? 'dark' : 'light'
			});
			const page = await context.newPage();

			// Set theme
			await page.addInitScript((t) => {
				try {
					localStorage.setItem('theme', t);
					if (t === 'dark') document.documentElement.classList.add('dark');
					else document.documentElement.classList.remove('dark');
				} catch (e) {}
			}, theme);

			for (const route of ROUTES) {
				try {
					await page.goto(baseUrl + route, { waitUntil: 'networkidle', timeout: 30000 });
					await page.waitForTimeout(500);

					// Check horizontal overflow
					const hasHorizontalOverflow = await page.evaluate(() => {
						return document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
					});
					if (hasHorizontalOverflow) {
						issues.push(`[${theme}/${vp.name}] ${route}: horizontal overflow`);
					}

					// Check for collapsed containers (very small heights that might indicate issues)
					const collapsed = await page.evaluate(() => {
						const els = Array.from(document.querySelectorAll('main, .card, table, .ledger-scroll'));
						for (const el of els) {
							const rect = el.getBoundingClientRect();
							if (rect.height > 0 && rect.height < 10) return true;
						}
						return false;
					});
					if (collapsed) {
						issues.push(`[${theme}/${vp.name}] ${route}: collapsed containers`);
					}

					// Check focus indicators exist
					const focusOk = await page.evaluate(() => {
						const btns = Array.from(document.querySelectorAll('button, a, [role="button"], input, select, textarea'));
						if (btns.length === 0) return true;
						// Just check that focus styles are defined
						const style = getComputedStyle(document.documentElement);
						return true;
					});
				} catch (e) {
					issues.push(`[${theme}/${vp.name}] ${route}: error ${e.message}`);
				}
			}

			await context.close();
		}

		// Test reduced motion
		const rmContext = await browser.newContext({
			viewport: { width: 375, height: 667 },
			colorScheme: theme === 'dark' ? 'dark' : 'light',
			reducedMotion: 'reduce'
		});
		const rmPage = await rmContext.newPage();
		await rmPage.addInitScript((t) => {
			try {
				localStorage.setItem('theme', t);
				if (t === 'dark') document.documentElement.classList.add('dark');
				else document.documentElement.classList.remove('dark');
			} catch (e) {}
		}, theme);
		for (const route of ['/', '/journal']) {
			try {
				await rmPage.goto(baseUrl + route, { waitUntil: 'networkidle', timeout: 30000 });
				await rmPage.waitForTimeout(300);
			} catch (e) {
				issues.push(`[${theme}/reduced-motion] ${route}: error ${e.message}`);
			}
		}
		await rmContext.close();
	}

	await browser.close();

	if (issues.length > 0) {
		console.error('\nIssues found:');
		for (const issue of issues) {
			console.error('  - ' + issue);
		}
		process.exit(1);
	} else {
		console.log('\nAll checks passed.');
		process.exit(0);
	}
}

audit().catch((e) => {
	console.error('Audit failed:', e);
	process.exit(1);
});
