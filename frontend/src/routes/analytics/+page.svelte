<script lang="ts">
	import { Activity } from 'lucide-svelte';
</script>

<svelte:head>
	<title>Analytics · Trading Journal</title>
</svelte:head>

<div class="mx-auto max-w-2xl">
	<div class="flex flex-col items-center gap-2 rounded-2xl border border-slate-200 px-6 py-14 text-center dark:border-slate-800">
		<span class="grid h-11 w-11 place-items-center rounded-full bg-emerald-500/10 text-emerald-500">
			<Activity size={20} />
		</span>
		<h1 class="text-lg font-semibold tracking-tight">Analytics arrive in Phase 4</h1>
		<p class="max-w-md text-sm text-slate-500 dark:text-slate-400">
			Equity curve, drawdown, R-distribution, win-rate donut, tag performance and the calendar
			heatmap will live here — powered by the <span class="font-mono text-[13px]">/api/analytics</span> endpoints.
		</p>
		<a
			href="/"
			class="mt-2 h-9 rounded-lg bg-emerald-500 px-4 text-sm font-medium leading-9 text-white transition-all duration-150 hover:bg-emerald-600 active:scale-[0.98]"
		>
			Back to trades
		</a>
	</div>
</div>
