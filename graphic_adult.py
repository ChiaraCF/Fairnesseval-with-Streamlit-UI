import itertools

import numpy as np
import os
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import seaborn as sns;

sns.set()  # for plot styling
import pandas as pd
from utils import mean_confidence_interval, aggregate_phase_time, get_last_results, add_combined_stats, get_info, \
    get_confidence_error
import matplotlib as mpl
# sns.set(rc={'figure.figsize':(8,6)})
# sns.set_context('notebook')
sns.set_style('whitegrid')
plt.rcParams.update({'font.size': 16, "figure.dpi": 400, 'savefig.dpi': 400, 'figure.figsize':(16*2/3,9*2/3)})
plt.rcParams['figure.constrained_layout.use'] = True
sns.set_context(rc={"legend.fontsize": 7.5})


# plt.rcParams["figure.figsize"] = (10,5)
# ax = global_df.pivot_table(index=['id', 'match_code'], columns=['dataset_code'], values=['pearson']).droplevel(0,1).groupby(['match_code']).plot(kind='box')
# ax['match'].get_figure().savefig(os.path.join(...))
# ax['nomatch'].get_figure().savefig(os.path.join(...), bbox_inches='tight')


class PlotUtility():
    columns = ['label', 'color']
    model_to_params_map = {
        'expgrad_fracs_e': ['expgrad sample', 'red'],
        'hybrid_5_e': ['hybrid 5 (LP)', 'gold'],
        'hybrid_5_U_e': ['hybrid 5 (E+U+LP)', 'gold'],
        'hybrid_1_e': ['hybrid 1 (GS only)', 'blue'],
        'hybrid_2_e': ['hybrid 2 (GS + pmf_predict)', 'cyan'],
        'hybrid_3_e': ['hybrid 3 (GS + LP)', 'brown'],
        'hybrid_4_e': ['hybrid 4 (GS + LP+)', 'magenta'],
        'hybrid_6_e': ['hybrid 6 (E+G+LP) E', 'DarkMagenta'],
        'hybrid_6_U_e': ['hybrid 6 (E+G+U+LP) E', 'DarkMagenta'],
        'combined_e': ['hybrid combined', 'lime'],
        'expgrad_fracs_g': ['expgrad sample G', 'IndianRed'],
        'hybrid_5_g': ['hybrid 5 (LP) G', 'GoldenRod'],
        'hybrid_5_U_g': ['hybrid 5 (LP) G', 'GoldenRod'],
        'hybrid_1_g': ['hybrid 1 (GS only) G', 'RoyalBlue'],
        'hybrid_2_g': ['hybrid 2 (GS + pmf_predict) G', 'DarkTurquoise'],
        'hybrid_3_g': ['hybrid 3 (GS + LP) G', 'LightSkyBlue'],
        'hybrid_4_g': ['hybrid 4 (GS + LP+) G', 'DarkMagenta'],
        'hybrid_6_g': ['hybrid 6 (E+G+LP) G', 'DarkMagenta'],
        'hybrid_6_U_g': ['hybrid 6 (E+G+LP) G', 'DarkMagenta'],
        'combined_g': ['hybrid combined G', 'LimeGreen'],
        'fairlearn_full': ['expgrad full', 'black'],
        'unmitigated': ['unmitigated', 'orange']}

    to_plot_models = [
        # 'expgrad_fracs_g',
        # 'hybrid_5_g',
        # 'hybrid_5_U_g',
        # 'hybrid_1_g',
        # 'hybrid_2_g',
        'hybrid_3_g',
        'hybrid_3_U_g',
        # 'hybrid_4_g',
        # 'hybrid_6_g',
        'hybrid_6_U_g',
        'expgrad_fracs_e',
        'hybrid_5_e',
        'hybrid_5_U_e',
        # 'hybrid_1_e',
        # 'hybrid_2_e',
        'hybrid_3_e',
        'hybrid_3_U_e',
        # 'hybrid_4_e',
        'hybrid_6_e',
        # 'hybrid_6_U_e',
        'fairlearn_full',
        'unmitigated']
    color_list = mpl.colormaps['tab20'].colors
    #sns.color_palette("hls", len(self.to_plot_models))
    # color_list = list(mcolors.TABLEAU_COLORS.keys())

    def __init__(self, all_model_df, x_axis='frac', y_axis='time', alphas=[0.05, 0.5, 0.95],
                 grid_fractions=[0.1, 0.2, 0.5], groupby_col='frac'):

        self.groupby_col = groupby_col
        self.fig = plt.figure()
        ax = plt.subplot()
        self.base_plot(all_model_df, x_axis, y_axis, alphas, grid_fractions, ax)
        ax.legend()
        self.ax = ax
        self.fig.show()

    def base_plot(self, all_model_df, x_axis, y_axis, alphas, grid_fractions, ax):
        def_alpha = .5
        all_model_df = all_model_df[all_model_df['model_name'].isin(self.to_plot_models)]
        time_aggregated_df = aggregate_phase_time(all_model_df)
        time_aggregated_df[self.groupby_col].fillna(1, inplace=True)
        self.x_values = time_aggregated_df[self.groupby_col].unique()
        self.n_points = len(self.x_values)
        # map_df = pd.DataFrame.from_dict(self.model_to_params_map, columns=self.columns, orient='index')
        to_iter = time_aggregated_df[time_aggregated_df['model_name'].isin(self.to_plot_models)].groupby(['model_name'],
                                                                                                         dropna=False)

        for model_name, turn_df in to_iter:
            # label, color = map_df.loc[model_name, ['label', 'color']].values
            label = model_name
            color = self.color_list[self.to_plot_models.index(model_name)]
            self.add_plot(ax, turn_df, x_axis, y_axis, color, label)
        ax.set_xlabel(f'{x_axis} (log scale)')
        ax.set_ylabel(y_axis)
        ax.set_title(f'{y_axis} v.s. {x_axis}')
        ax.set_xscale("log")
        if y_axis == 'time':
            ax.set_yscale("log")

    def add_plot(self, ax, turn_df, x_axis, y_axis, color, label):
        agg_x_axis = self.groupby_col if x_axis == 'time' else x_axis
        index_cols = ['random_seed', 'train_test_fold']
        turn_data = turn_df.pivot(index=index_cols, columns=agg_x_axis, values=y_axis)
        ci = mean_confidence_interval(turn_data)
        y_values = ci[0]
        if x_axis == 'time':
            time_data = turn_df.pivot(index=index_cols, columns=agg_x_axis, values='time')
            ci_x = mean_confidence_interval(time_data)
            xerr = (ci_x[2] - ci_x[1]) / 2
            yerr = (ci[2] - ci[1]) / 2
            x_values = ci_x[0]
            if len(y_values) == 1:
                ax.axhline(y_values, linestyle="-.", color=color, zorder=10)
            zorder = 10 if len(y_values) == 1 else None
            ax.errorbar(x_values, y_values, xerr=xerr, yerr=yerr, color=color, label=label, fmt='--o', zorder=zorder)
        else:
            x_values = turn_data.columns
            ax.fill_between(x_values, ci[1], ci[2], color=color, alpha=0.3)
            if len(y_values) == 1:
                ax.plot(self.x_values, np.repeat(y_values, self.n_points), "-.", color=color, zorder=10, label=label)
            else:
                ax.plot(x_values, y_values, color, label=label, marker="o", linestyle='--')

    def save(self, base_dir, dataset_name, name, fig=None):
        if fig is None:
            fig = self.fig
        self.save_figure(base_dir, dataset_name, name, fig)

    @staticmethod
    def save_figure(base_dir, dataset_name, name, fig=None):
        host_name, current_time_str = get_info()
        base_dir = os.path.join(base_dir, dataset_name, host_name)
        path = os.path.join(base_dir, f'{current_time_str}_{name}')
        last_path = os.path.join(base_dir, f'last_{name}')
        try:
            os.makedirs(base_dir)
        except:
            pass
        for full_path in [
            # path,
            last_path]:
            fig.savefig(full_path + '.svg', format='svg')
            fig.savefig(full_path + '.png')


def time_stacked_by_phase(df, ax, fig: plt.figure):
    fig.set_figheight(8)
    fig.set_figwidth(20)
    to_plot = df.groupby(['frac', 'model_name', 'phase']).agg(
        {'time': ['mean', ('error', get_confidence_error)]}).unstack(['phase'])
    yerr = to_plot.loc[:, ('time', 'error', slice(None))]
    to_plot.plot.bar(stacked=True, y=('time', 'mean'), yerr=yerr.values.T, rot=45, ax=ax)


def phase_time_vs_frac(df, ax, fig, y_log=True):
    to_plot = df.groupby(['frac', 'phase']).agg({'time': ['mean', ('error', get_confidence_error)]}).unstack('phase')
    yerr = to_plot.loc[:, ('time', 'error', slice(None))]
    to_plot.plot(y=('time', 'mean'), yerr=yerr.values.T, rot=0, ax=ax, ylabel='time')
    if y_log:
        ax.set_yscale("log")
        ax.set_ylabel('time (log)')


if __name__ == '__main__':
    save = True
    base_dir = os.path.join("results", "fairlearn-2", "adult")
    all_model_df = get_last_results(base_dir)
    all_model_df = add_combined_stats(all_model_df)
    missed_conf = np.setdiff1d(all_model_df['model_name'].unique(),
                               list(PlotUtility.model_to_params_map.keys())).tolist()
    assert len(missed_conf) == 0, missed_conf
    base_plot_dir = os.path.join('results', 'plots')

    df = all_model_df.copy()
    df = df[df['model_name'].isin(PlotUtility.to_plot_models)]
    model_name_map = {name: '_'.join([x[0] for x in name.split("_")]) for name in df['model_name'].unique()}
    df['model_name'] = df['model_name'].map(model_name_map)
    for name, plot_f in [['time_stacked_by_phase', time_stacked_by_phase],
                         ['phase_time_vs_frac', phase_time_vs_frac]
                         ]:
        fig, ax = plt.subplots()
        plot_f(df, ax=ax, fig=fig)
        plt.show()
        if save is True:
            PlotUtility.save_figure(base_plot_dir, dataset_name='adult', name=name, fig=fig)

    pl = PlotUtility(all_model_df, x_axis='frac', y_axis='time')
    if save is True:
        pl.save(base_plot_dir, dataset_name='adult', name=f'frac_vs_time')

    to_iter = list(itertools.product(['train', 'test'], ['violation', 'error'], [
        # 'frac',
        'time']))
    for phase, metric_name, x_axis in to_iter:
        turn_plot = PlotUtility(all_model_df, y_axis=f'{phase}_{metric_name}', x_axis=x_axis)
        if save is True:
            turn_plot.save(base_plot_dir, dataset_name='adult', name=f'{phase}_{metric_name}_vs_{x_axis}')
